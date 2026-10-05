"""Print synthetic terminal acceptance samples; never read or write configuration."""
from __future__ import annotations


def main() -> None:
    escape = "\x1b["

    def line(style: str, text: str) -> None:
        print(f"{escape}{style}m{text}{escape}0m")

    print("One-Tone synthetic diagnostic: record host, version, Seed, Mode and session.")
    print("These samples do not prove application or SSH visual acceptance.")
    line("0", "default: document body /sample/project version 1.0 status READY")
    line("39;40", "default foreground on ANSI black background: document body")
    line("37;40", "ANSI white on ANSI black: status READY /sample/project")
    line("30;47", "ANSI black on ANSI white: reversed status /sample/project")
    for code in (*range(30, 38), *range(90, 98)):
        line(str(code), f"ANSI16 {code}: syntax /sample/project version 1.0 placeholder >")
    for index in (16, 22, 46, 59, 196, 226, 231, 244, 250):
        line(f"38;5;{index}", f"ANSI256 {index}: path /sample/project status READY")
    for red, green, blue in ((32, 36, 40), (128, 128, 128), (230, 230, 230), (200, 60, 60)):
        line(f"38;2;{red};{green};{blue}", f"RGB {red},{green},{blue}: input placeholder >")
    line("38;2;24;28;32;48;2;20;24;30", "application-owned dark region: body / status / syntax")
    line("2", "dim: functional path /sample/project version 1.0 placeholder >")
    line("7", "reverse: status READY / keyboard hint Enter")
    line("2;7", "dim + reverse: status / path / placeholder >")
    line("0", "selection: manually select this body, then ANSI, RGB and dim text above.")


if __name__ == "__main__":
    main()
