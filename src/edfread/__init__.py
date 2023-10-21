"""Read eye-tracking information from EyeLink EDF files."""

from edfread.parse import read_edf, save_human_understandable as save_h5
from edfread.edf_read import read_preamble, read_messages, read_calibration
