from argparse import ArgumentParser
from functools import wraps
from io import BytesIO
from pathlib import Path

from PIL import Image


def read_string(io, offset: int = 0, maxlen: int = 0, encoding: str = "utf-8") -> str:
    """ Reads a null terminated string from the specified address """

    length = 0
    string = ""

    io.seek(offset)
    while (char := io.read(1)) != b"\x00":
        try:
            string += char.decode(encoding)
            length += 1
        except UnicodeDecodeError:
            raise UnicodeDecodeError(
                f"{char} at pos {length} is not a valid {encoding} character")

        if length > (maxlen-1) and maxlen != 0:
            return string

    return string


def io_preserve(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        _loc = self._rawdata.tell()
        value = func(self, *args, **kwargs)
        self._rawdata.seek(_loc)
        return value
    return wrapper


class Regions:
    AMERICA = 0
    EUROPE = 1
    JAPAN = 2


class Jobs:
    COMPILE = "COMPILE"
    EXTRACT = "EXTRACT"


class RGB5A1(object):

    TileWidth = 4
    TileHeight = 4

    @staticmethod
    def encode_pixel(pixel: tuple) -> int:
        """ RGB888 or RGBA8888 ONLY """
        r = (pixel[0] >> 3) & 0b11111
        g = (pixel[1] >> 3) & 0b11111
        b = (pixel[2] >> 3) & 0b11111

        if len(pixel) == 3:
            a = 1
        else:
            a = 1 if pixel[3] & 0x80 else 0

        return (a << 15) | (r << 10) | (g << 5) | b

    @staticmethod
    def decode_pixel(pixel: int) -> tuple:
        """ RGBA8888 ONLY """
        r = ((pixel >> 10) & 0b11111) * 8
        g = ((pixel >> 5) & 0b11111) * 8
        b = (pixel & 0b11111) * 8
        a = (pixel >> 15) * 0xFF

        return (r, g, b, a)


class BNR(RGB5A1):
    ImageWidth = 96
    ImageHeight = 32

    ImgTileWidth = ImageWidth // RGB5A1.TileWidth
    ImgTileHeight = ImageHeight // RGB5A1.TileHeight

    def __init__(self, f: Path, region: Regions = Regions.AMERICA, gameName: str = "", gameTitle: str = "", companyName: str = "", companyTitle: str = "", desc: str = ""):
        self._rawdata = BytesIO(b"\x00" * 0x1960)
        self.load(f, region, gameName, gameTitle,
                  companyName, companyTitle, desc)

    @property
    @io_preserve
    def magic(self) -> str:
        self._rawdata.seek(0)
        return str(self._rawdata.read(4))

    @magic.setter
    @io_preserve
    def magic(self, region: Regions):
        self._rawdata.seek(0)

        if region in (Regions.AMERICA, Regions.JAPAN):
            self._rawdata.write(b"BNR1")
        elif region == Regions.EUROPE:
            self._rawdata.write(b"BNR2")
        else:
            raise NotImplementedError(f"Unknown region type {region} provided")

    @property
    @io_preserve
    def rawImage(self) -> BytesIO:
        self._rawdata.seek(0x20)
        return BytesIO(self._rawdata.read(0x1800))

    @rawImage.setter
    @io_preserve
    def rawImage(self, _img: [bytes, BytesIO, Image.Image]):
        self._rawdata.seek(0x20)
        if isinstance(_img, bytes):
            self._rawdata.write(_img[:0x1800])
        elif isinstance(_img, BytesIO):
            self._rawdata.write(_img.getvalue()[:1800])
        elif isinstance(_img, Image.Image):
            smallImg = _img.resize((BNR.ImageWidth, BNR.ImageHeight))
            for yBlock in range(BNR.ImgTileHeight):
                for xBlock in range(BNR.ImgTileWidth):
                    for iy in range(BNR.TileHeight):
                        for ix in range(BNR.TileWidth):
                            x = xBlock*BNR.TileWidth + ix
                            y = yBlock*BNR.TileHeight + iy

                            pixel = smallImg.getpixel((x, y))
                            if x < BNR.ImageWidth and y < BNR.ImageHeight:
                                self._rawdata.write(self.encode_pixel(
                                    pixel).to_bytes(2, "big", signed=False))

    @property
    @io_preserve
    def gameName(self) -> str:
        return read_string(self._rawdata, 0x1820, 0x20, encoding="ascii")

    @gameName.setter
    @io_preserve
    def gameName(self, name: str):
        self._rawdata.seek(0x1820)
        self._rawdata.write(bytes(name[:0x1F], "ascii") + b"\x00")

    @property
    @io_preserve
    def developerName(self) -> str:
        return read_string(self._rawdata, 0x1840, 0x20, encoding="ascii")

    @developerName.setter
    @io_preserve
    def developerName(self, name: str):
        self._rawdata.seek(0x1840)
        self._rawdata.write(bytes(name[:0x1F], "ascii") + b"\x00")

    @property
    @io_preserve
    def gameTitle(self) -> str:
        return read_string(self._rawdata, 0x1860, 0x40, encoding="ascii")

    @gameTitle.setter
    @io_preserve
    def gameTitle(self, name: str):
        self._rawdata.seek(0x1860)
        self._rawdata.write(bytes(name[:0x3F], "ascii") + b"\x00")

    @property
    @io_preserve
    def developerTitle(self) -> str:
        return read_string(self._rawdata, 0x18A0, 0x40, encoding="ascii")

    @developerTitle.setter
    @io_preserve
    def developerTitle(self, name: str):
        self._rawdata.seek(0x18A0)
        self._rawdata.write(bytes(name[:0x3F], "ascii") + b"\x00")

    @property
    @io_preserve
    def gameDescription(self) -> str:
        return read_string(self._rawdata, 0x18E0, 0x80, encoding="ascii")

    @gameDescription.setter
    @io_preserve
    def gameDescription(self, name: str):
        self._rawdata.seek(0x18E0)
        self._rawdata.write(bytes(name[:0x7F], "ascii") + b"\x00")

    def getImage(self) -> Image:
        _image = self.rawImage
        img = Image.new("RGBA", (BNR.ImageWidth, BNR.ImageHeight))

        for yBlock in range(BNR.ImgTileHeight):
            for xBlock in range(BNR.ImgTileWidth):
                for iy in range(BNR.TileHeight):
                    for ix in range(BNR.TileWidth):
                        x = xBlock*BNR.TileWidth + ix
                        y = yBlock*BNR.TileHeight + iy

                        pixel = int.from_bytes(
                            _image.read(2), "big", signed=False)
                        if x < BNR.ImageWidth and y < BNR.ImageHeight:
                            img.putpixel((x, y), self.decode_pixel(pixel))

        return img

    def save(self, dest: Path):
        dest.write_bytes(self._rawdata.getvalue())

    def load(self, f: Path, region: Regions = Regions.AMERICA, gameName: str = "", gameTitle: str = "", companyName: str = "", companyTitle: str = "", desc: str = "", overwrite: bool = False):
        if f.suffix == ".bnr":
            self._rawdata.write(f.read_bytes())
            if overwrite:
                self.magic = region
                self.gameName = gameName
                self.gameTitle = gameTitle
                self.companyName = companyName
                self.companyTitle = companyTitle
                self.gameDescription = desc
        elif f.suffix in (".png", ".jpeg"):
            self.magic = region
            self.gameName = gameName
            self.gameTitle = gameTitle
            self.companyName = companyName
            self.companyTitle = companyTitle
            self.gameDescription = desc

            self.rawImage = Image.open(f)


if __name__ == "__main__":
    parser = ArgumentParser(
        "BNR Parser", description="Tool to extract and compile bnr files")

    parser.add_argument("bnr", help="bnr file")
    parser.add_argument("img", help="png or jpeg image")
    parser.add_argument("-j", "--job",
                        help="Job to execute",
                        choices=[Jobs.EXTRACT, Jobs.COMPILE],
                        default=Jobs.COMPILE)
    parser.add_argument("-g", "--gamename",
                        help="Game short name",
                        default="",
                        metavar="STR")
    parser.add_argument("-G", "--gametitle",
                        help="Game long name",
                        default="",
                        metavar="STR")
    parser.add_argument("-d", "--devname",
                        help="Developer short name",
                        default="",
                        metavar="STR")
    parser.add_argument("-D", "--devtitle",
                        help="Developer long name",
                        default="",
                        metavar="STR")
    parser.add_argument("--desc",
                        help="Game description",
                        default="",
                        metavar="STR")
    parser.add_argument("-r", "--region",
                        help="Game region",
                        choices=["E", "P", "J"],
                        default="E")

    args = parser.parse_args()

    if args.region == "E":
        region = Regions.AMERICA
    elif args.region == "P":
        region = Regions.EUROPE
    elif args.region == "J":
        region = Regions.JAPAN
    else:
        raise NotImplementedError(
            f"Unknown region type {args.region} provided")

    if args.job == Jobs.COMPILE:
        bnr = BNR(Path(args.img).resolve(),
                  region,
                  args.gamename,
                  args.gametitle,
                  args.devname,
                  args.devtitle,
                  args.desc)

        bnr.save(Path(args.bnr).resolve())
    elif args.job == Jobs.EXTRACT:
        bnr = BNR(Path(args.bnr).resolve())

        img = bnr.getImage()
        img.save(str(Path(args.img).resolve()))
