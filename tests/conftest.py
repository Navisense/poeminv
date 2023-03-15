import pathlib
import sys

sys.path[:0] = [
    str(pathlib.Path(__file__).parent),
    str(pathlib.Path(__file__).parent.parent / 'port_emission_inventory')]
