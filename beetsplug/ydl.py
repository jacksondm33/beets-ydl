import logging
import mutagen
import re
import subprocess
from optparse import OptionParser
from yt_dlp import YoutubeDL
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

logger = logging.getLogger("ydl")


class BeetsYdlPlugin(BeetsPlugin):
    def __init__(self):
        super(BeetsYdlPlugin, self).__init__()
        self.config.add(
            {
                "verbose": False,
                "cachedir": "ydl",
                "outtmpl": "%(id)s.%(ext)s",
                "ym_search_format": "https://music.youtube.com/search?q={artist}+{song}#songs",
                "youtubedl_config": {
                    "verbose": False,
                    "keepvideo": False,
                    "restrictfilenames": True,
                    "quiet": True,
                    "format": "bestaudio[acodec=opus]/best[acodec=opus]",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "opus",
                            "preferredquality": "192",
                        }
                    ],
                    "playlist_items": "1",
                },
                "youtubedl_info_config": {
                    "verbose": False,
                    "quiet": True,
                    "simulate": True,
                },
            }
        )

    def commands(self):
        def ydl_func(lib, opts, args):
            self.config.set_args(opts)
            return self.run_ydl(args)

        def ymdl_func(lib, opts, args):
            self.config.set_args(opts)
            urls = []
            for arg in args:
                urls += self.get_ym_urls(arg)
            return self.run_ydl(urls)

        parser = OptionParser()
        parser.add_option(
            "--no-import",
            action="store_false",
            default=True,
            dest="import",
            help="do not import into beets after downloading",
        )
        parser.add_option(
            "--no-download",
            action="store_false",
            default=True,
            dest="download",
            help="do not download any files",
        )
        parser.add_option(
            "-f",
            "--force-download",
            action="store_true",
            default=False,
            dest="force_download",
            help="always download and overwrite files",
        )
        parser.add_option(
            "-k",
            "--keep-files",
            action="store_true",
            default=False,
            dest="keep_files",
            help="keep the files downloaded on cache",
        )
        parser.add_option(
            "-v",
            "--verbose",
            action="store_true",
            dest="verbose",
            default=False,
            help="print processing information",
        )
        ydl_command = Subcommand(
            "ydl", parser=parser, help="download music from YouTube"
        )
        ymdl_command = Subcommand(
            "ymdl", parser=parser, help="download music from YouTube Music"
        )
        ydl_command.func = ydl_func
        ymdl_command.func = ymdl_func

        return [ydl_command, ymdl_command]

    def run_ydl(self, args):
        """Run `ydl` command."""
        if self.config["download"].get():
            for arg in args:
                self.download_url(arg)
        if self.config["import"].get():
            self.beets_import([self.config["cachedir"].as_filename()])

    def get_ym_urls(self, url):
        """Get YouTube Music url(s) from the given url."""
        logger.debug("Downloading info: " + url)
        youtubedl_config = self.config["youtubedl_info_config"].get()
        ydl = YoutubeDL(youtubedl_config)
        info = ydl.sanitize_info(ydl.extract_info(url))
        ym_urls = []
        if "entries" not in info:
            info = {"entries": [info]}
        for entry in info["entries"]:
            if ("artists" in entry) and ("track" in entry):
                artist, song = (", ".join(entry["artists"]), entry["track"])
            else:
                artist, song = self.parse_title(entry["title"])
            # album = entry["album"] if "album" in entry else ""
            artist_urlified = "+".join(artist.split())
            song_urlified = "+".join(song.split())
            ym_urls.append(
                self.config["ym_search_format"]
                .get()
                .format(artist=artist_urlified, song=song_urlified)
            )
        return ym_urls

    def download_url(self, url):
        """Download a song from url."""
        logger.debug("Downloading: " + url)
        youtubedl_config = self.config["youtubedl_config"].get()
        youtubedl_config["outtmpl"] = (
            self.config["cachedir"].as_filename() + "/" + self.config["outtmpl"].get()
        )
        youtubedl_config["nooverwrites"] = not self.config["force_download"].get()
        youtubedl_config["postprocessors"][0]["nopostoverwrites"] = not self.config[
            "force_download"
        ].get()
        ydl = YoutubeDL(youtubedl_config)
        info = ydl.sanitize_info(ydl.extract_info(url))
        if "entries" in info:
            info = info["entries"][0]
        if ("album" in info) and ("artists" in info) and ("track" in info):
            # album, artist, song = (info["album"], ", ".join(info["artists"]), info["track"])
            album, artist, song = (info["album"], info["artists"][0], info["track"])
        else:
            album, artist, song = self.parse_description(info["description"])
            logger.warning("Parsed description: %s - %s (%s)" % (artist, song, album))
        print("Downloaded: %s - %s (%s)" % (artist, song, album))
        filename = youtubedl_config["outtmpl"]["default"] % {
            "id": info["id"],
            "ext": youtubedl_config["postprocessors"][0]["preferredcodec"],
        }
        self.write_tags(filename, album, artist, song)
        return filename

    def clean_str(self, s):
        """Remove extraneous whitespace from `s`."""
        s = re.sub(r"\s+", " ", s)
        s = s.strip()
        return s

    def parse_title(self, title):
        """Parse artist and song from title."""
        logger.debug("Parsing title: `%s`" % title)
        regex = re.compile(
            r"""^([^-~|*%#:_'"`]*)[-~|*%#:_]?\s*(?P<quote>['"`]?)(.*)(?P=quote)"""
        )
        if regex.match(title):
            artist, _, song = regex.findall(title)[0]
            return (self.clean_str(artist), self.clean_str(song))
        return (self.clean_str(title), self.clean_str(title))

    def parse_description(self, title):
        """Parse album, artist, and song from description."""
        # TODO: Implement properly
        artist, song = self.parse_title(title)
        return ("", artist, song)

    def write_tags(self, filename, album, artist, song):
        """Write tags to audio file."""
        # logger.debug("Writing tags: %s - %s (%s)" % (artist, song, album))
        file_info = mutagen.File(filename)
        file_info["album"] = album
        file_info["artist"] = artist
        file_info["title"] = song
        file_info.save()

    def beets_import(self, filenames):
        """Import a list of file names to beets."""
        logger.debug("Importing: %s" % filenames)
        command = ["beet"]
        if self.config["verbose"].get():
            command.extend(["-v"])
        command.extend(["import", "-g"])
        if self.config["keep_files"].get():
            command.extend(["-c"])
        else:
            command.extend(["-m"])
        command.extend(filenames)
        logger.debug("Running: %s" % command)
        subprocess.run(command)
