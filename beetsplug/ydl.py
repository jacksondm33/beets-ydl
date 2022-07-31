import mutagen
import re
import subprocess
from optparse import OptionParser
from yt_dlp import YoutubeDL
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand


class BeetsYdlPlugin(BeetsPlugin):

    def __init__(self):
        super(BeetsYdlPlugin, self).__init__()
        self.config.add({
            'verbose': False,
            'cachedir': 'ydl',
            'outtmpl': '%(id)s.%(ext)s',
            'youtubedl_config': {
                'verbose': False,
                'keepvideo': False,
                'restrictfilenames': True,
                'quiet': True,
                'format': 'bestaudio[acodec=opus]/best[acodec=opus]',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'opus',
                    'preferredquality': '192'
                }]
            }
        })

    def commands(self):

        def ydl_func(lib, opts, args):
            self.config.set_args(opts)
            for arg in args:
                self.run_ydl(lib, opts, arg)

        parser = OptionParser()
        parser.add_option("--no-import",
                          action="store_false",
                          default=True,
                          dest="import",
                          help="do not import into beets after downloading")
        parser.add_option("-f",
                          "--force-download",
                          action="store_true",
                          default=False,
                          dest="force_download",
                          help="always download and overwrite files")
        parser.add_option("-k",
                          "--keep-files",
                          action="store_true",
                          default=False,
                          dest="keep_files",
                          help="keep the files downloaded on cache")
        parser.add_option("-v",
                          "--verbose",
                          action="store_true",
                          dest="verbose",
                          default=False,
                          help="print processing information")
        ydl_command = Subcommand("ydl",
                                 parser=parser,
                                 help="download music from YouTube")
        ydl_command.func = ydl_func

        return [ydl_command]

    def run_ydl(self, lib, opts, arg):
        """Run `ydl` command."""
        if self.config["verbose"].get():
            print("[ydl] Downloading: " + arg)
        youtubedl_config = self.config["youtubedl_config"].get()
        youtubedl_config["outtmpl"] = self.config["cachedir"].as_filename() + '/' + self.config["outtmpl"].get()
        youtubedl_config["nooverwrites"] = not self.config["force_download"].get()
        youtubedl_config["postprocessors"][0]["nopostoverwrites"] = not self.config["force_download"].get()
        ydl = YoutubeDL(youtubedl_config)
        info = ydl.sanitize_info(ydl.extract_info(arg))
        if ("artist" in info) and ("track" in info):
            artist, song = (info["artist"], info["track"])
        else:
            artist, song = self.parse_title(info["title"])
        filename = youtubedl_config["outtmpl"]["default"] % {
            "id": info["id"],
            "ext": youtubedl_config["postprocessors"][0]["preferredcodec"]
        }
        self.write_tags(filename, artist, song)
        if self.config["import"].get():
            self.beets_import(filename)

    def clean_str(self, s):
        """Remove extraneous whitespace from `s`."""
        s = re.sub(r"\s+", " ", s)
        s = s.strip()
        return s

    def parse_title(self, title):
        """Parse artist and song from title."""
        if self.config["verbose"].get():
            print("[ydl] Parsing title: `%s`" % title)
        regex = re.compile(
            r"""^([^-~|*%#:_'"`]*)[-~|*%#:_]?\s*(?P<quote>['"`]?)(.*)(?P=quote)"""
        )
        if regex.match(title):
            artist, _, song = regex.findall(title)[0]
            return (self.clean_str(artist), self.clean_str(song))
        return (self.clean_str(title), self.clean_str(title))

    def write_tags(self, filename, artist, song):
        """Write tags to audio file."""
        if self.config["verbose"].get():
            print("[ydl] Writing tags: %s - %s" % (artist, song))
        file_info = mutagen.File(filename)
        file_info["artist"] = artist
        file_info["title"] = song
        file_info.save()

    def beets_import(self, filename):
        """Import `filename` to beets."""
        if self.config["verbose"].get():
            print("[ydl] Importing: " + filename)
        command = ["beet"]
        if self.config["verbose"].get():
            command.extend(["-v"])
        command.extend(["import", "-s"])
        if self.config["keep_files"].get():
            command.extend(["-c"])
        else:
            command.extend(["-m"])
        command.extend([filename])
        if self.config["verbose"].get():
            print("[ydl] Running: %s" % command)
        subprocess.run(command)
