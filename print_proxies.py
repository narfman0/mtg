#!/usr/bin/env python3
"""Print proxy PDFs (MPCFill etc.) on the Epson ET-8500 with known-good settings.

Usage: print_proxies.py -p <stock> <file.pdf>
       print_proxies.py --list            (show what the driver actually offers)

-p is mandatory and has no default: it is the point in the run where you assert
what is physically in the tray. Nothing prints until you say what you loaded.

Why this exists -- the two things that ruin a proxy sheet:

1. Silent rescaling. CUPS will happily resample a 300 DPI card sheet to "fit"
   the page; that softens 6pt rules text. We always pass print-scaling=none so
   the PDF goes down at true 100%, and we abort if the PDF page size does not
   match the media size (with scaling off, a mismatch clips instead of shrinks).

2. The wrong black. The ET-8500 carries two blacks -- MB (pigment matte) and
   PB (dye photo) -- and the driver picks between them from the media type, not
   from the paper you actually loaded. Pigment on matte stock gives the crispest
   small text; dye on glossy stock keeps photo blacks deep and non-smearing.
   Mismatch either way and text looks "off". Pick the -p entry for your stock.

Foil/metallic stock prints dark because there is no white ink laying an opaque
base under the CMYK -- the mirror substrate reflects the room, not a lamp. Feed
it with the "thick" stock and lighten the PDF itself before printing; driver
brightness cannot add the white layer that is missing.
"""
import argparse
import os
import re
import subprocess
import sys

PRINTER = "EPSON_ET_8500"

# stock -> MediaType, which encodes both the paper and the quality tier
# (_HIGH = best). Matte entries route text through the pigment black (MB),
# glossy entries through the photo black (PB) -- see the note up top.
STOCKS = {
    "vinyl":       "PMMATT_HIGH",      # matte vinyl sticker sheets
    "vinyl-gloss": "PLATINA_HIGH",     # glossy vinyl sticker sheets
    "matte":       "PMMATT_HIGH",      # matte proxy cardstock
    "thick":       "THICK1_HIGH",      # heavy cardstock, incl. foil/metallic
    "thicker":     "THICK2_HIGH",      # heaviest the feeder takes
    "glossy":      "PLATINA_HIGH",
    "semigloss":   "PMPHOTO_HIGH",
    "ultraglossy": "LCPP_HIGH",
    "fineart":     "VELVET_FINE_HIGH",
    "plain":       "PLAIN_HIGH",       # cheap test prints on copy paper
}

# PageSize -> (width, height) in points, for the no-scaling sanity check.
MEDIA_PTS = {
    "Letter": (612, 792), "Legal": (612, 1008), "A4": (595.28, 841.89),
    "A5": (419.53, 595.28), "A6": (297.64, 419.53), "B5": (498.9, 708.66),
    "B6": (354.33, 498.9), "4X6FULL": (288, 432), "4X7": (288, 504),
    "8x10": (576, 720), "2L": (360, 504.57), "Postcard": (283.46, 419.53),
}

INPUT_SLOT = "RearPaperFeed"  # the straight path; cardstock and vinyl need it
LOW_INK = 20  # percent

# _HIGH is the top quality tier the ESC/P-R driver exposes -- there is no
# separate resolution knob, so the suffix is the whole quality setting. Every
# stock above must use it; this is the guard against a _NORMAL creeping in.
assert all(v.endswith("_HIGH") for v in STOCKS.values()), STOCKS


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def driver_options(printer):
    """Parse `lpoptions -l` into {option: [choices]} so we only send valid values."""
    opts = {}
    for line in run(["lpoptions", "-p", printer, "-l"]).splitlines():
        key, _, rest = line.partition(":")
        if rest:
            opts[key.split("/")[0]] = [c.lstrip("*") for c in rest.split()]
    return opts


def check_printer(printer):
    state = run(["lpstat", "-p", printer])
    if not state.strip():
        sys.exit(f"no such printer queue {printer!r} (see: lpstat -p)")
    if "disabled" in state or "stopped" in state:
        sys.exit(f"printer is not accepting jobs:\n{state.strip()}\n"
                 f"resume with: cupsenable {printer}")

    defaults = run(["lpoptions", "-p", printer])
    names = re.search(r"marker-names=('[^']*'|\S+)", defaults)
    levels = re.search(r"marker-levels=('[^']*'|\S+)", defaults)
    if names and levels:
        pairs = zip(names.group(1).strip("'").split(","),
                    levels.group(1).strip("'").split(","))
        low = [f"{n}={v}%" for n, v in pairs if v.lstrip("-").isdigit()
               and 0 <= int(v) < LOW_INK]
        if low:
            print(f"warning: low ink -- {', '.join(low)} "
                  f"(a starved GY/PB channel shows up first in small text)")


def pdf_page_size(path):
    """(width, height) in points of the PDF's first page, or None."""
    m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", run(["pdfinfo", path]))
    return (float(m.group(1)), float(m.group(2))) if m else None


def check_page_size(path, page_size):
    pdf = pdf_page_size(path)
    want = MEDIA_PTS.get(page_size.lstrip("T"))
    if not pdf or not want:
        return
    ok = (all(abs(a - b) <= 2 for a, b in zip(pdf, want))
          or all(abs(a - b) <= 2 for a, b in zip(pdf[::-1], want)))
    if ok:
        return
    sys.exit(f"PDF page is {pdf[0]:.0f}x{pdf[1]:.0f} pts but media {page_size} is "
             f"{want[0]:.0f}x{want[1]:.0f} pts. Scaling is off by design, so this "
             f"would clip or offset the cards rather than resize them.\n"
             f"Re-export the PDF at {page_size}, or pass --media for the size it is.")


def build_options(args, avail):
    opts = {
        "print-scaling": "none",   # true 100% -- never let CUPS resample the art
        "number-up": "1",
        "Duplex": "None",
        "Ink": "COLOR",
        "MediaType": STOCKS[args.stock],
        "PageSize": args.page_size,
        "InputSlot": INPUT_SLOT,
    }
    for key, val in sorted(opts.items()):
        choices = avail.get(key)
        if choices and val not in choices:
            sys.exit(f"driver rejects {key}={val}; choices: {' '.join(choices)}")
    return opts


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("pdf", nargs="?", help="PDF to print")
    p.add_argument("-P", "--printer", default=PRINTER)
    p.add_argument("-p", "--stock", choices=sorted(STOCKS),
                   help="what is loaded in the tray; required, no default")
    p.add_argument("-n", "--copies", type=int, default=1)
    p.add_argument("--pages", help="page range, e.g. 1 or 2-4")
    p.add_argument("--media", dest="page_size", default="Letter")
    p.add_argument("--test", action="store_true",
                   help="one page on plain paper, to check layout before using stock")
    p.add_argument("--dry-run", action="store_true", help="show the lp command only")
    p.add_argument("--list", action="store_true",
                   help="print the driver's own option list and exit")
    args = p.parse_args()

    avail = driver_options(args.printer)
    if args.list:
        for key, choices in sorted(avail.items()):
            print(f"{key}: {' '.join(choices)}")
        return
    if not args.pdf:
        p.error("a PDF is required")
    if not os.path.isfile(args.pdf):
        sys.exit(f"no such file: {args.pdf}")

    if args.test:
        if args.stock:
            sys.exit("--test prints on plain paper; drop -p")
        args.stock = "plain"
        args.pages = args.pages or "1"
    elif not args.stock:
        sys.exit("pass -p to confirm what is loaded in the tray, e.g. -p vinyl\n"
                 f"choices: {', '.join(sorted(STOCKS))}")

    check_printer(args.printer)
    check_page_size(args.pdf, args.page_size)

    opts = build_options(args, avail)
    cmd = ["lp", "-d", args.printer, "-n", str(args.copies),
           "-t", os.path.basename(args.pdf)]
    if args.pages:
        cmd += ["-P", args.pages]
    for key, val in sorted(opts.items()):
        cmd += ["-o", f"{key}={val}"]
    cmd.append(args.pdf)

    pdf = pdf_page_size(args.pdf)
    size = f"{pdf[0] / 72:.2f}x{pdf[1] / 72:.2f} in" if pdf else "unknown size"
    print(f"{args.pdf} ({size}) -> {args.printer} "
          f"[{args.stock}: {opts['MediaType']}, {opts['PageSize']}, "
          f"scaling off]")
    if args.dry_run:
        print(" ".join(cmd))
        return
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
