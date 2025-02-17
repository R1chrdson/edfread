import argparse
import json
import os

import h5py
import numpy as np
import pandas as pd

from edfread import edf_read


def read_edf(
    filename,
    ignore_samples=False,
    message_filter=None,
    trial_marker="TRIALID",
):
    """
    Parse an EDF file into a pandas.DataFrame.

    EDF files contain three types of data: samples, events and
    messages. Samples are what is recorded by the eye-tracker at each
    point in time. This contains for example instantaneous gaze
    position and pupil size. Events abstract from samples by defining
    fixations, saccades and blinks. Messages contain meta information
    about the recording such as user defined information and
    calibration information etc.

    Parameters
    ----------
    filename : str
        Path to EDF file.

    ignore_samples : bool
        If true individual samples will not be saved, but only event
        averages.

    message_filter : list of str, optional
        Messages are kept only if they start with one of these strings.

    trial_marker : str, optional
        Messages that start with this string will be assumed to
        indicate the start of a trial.

    Returns
    -------
    samples : pandas.DataFrame
        Sample information, including time, x, y, and pupil size.

    events : pandas.DataFrame
        Event information, including saccades and fixations.

    messages : pandas.DataFrame
        Message information.
    """
    if not os.path.isfile(filename):
        raise RuntimeError(f"File does not exist: {filename}")

    samples, events, messages = edf_read.parse_edf(
        filename, ignore_samples, message_filter, trial_marker
    )
    events = pd.DataFrame(events)
    messages = pd.DataFrame(messages)
    samples = pd.DataFrame(np.asarray(samples), columns=edf_read.sample_columns)
    return samples, events, messages


def trials2events(events, messages):
    """Match trial meta information to individual events."""
    return events.merge(messages, how="left", on=["trial"])


def save_h5(data, path):
    """Save HDF with explicit mapping of string to numbers."""
    f = h5py.File(path, "w")
    try:
        for name, table in data.items():
            fm_group = f.create_group(name)
            for field in table.columns:
                try:
                    fm_group.create_dataset(
                        field,
                        data=table[field],
                        compression="gzip",
                        compression_opts=1,
                    )
                except TypeError:
                    # Probably a string that can not be saved in hdf.
                    # Map to numbers and save mapping in attrs.
                    column = table[field].values.astype(str)
                    mapping = dict((key, i) for i, key in enumerate(np.unique(column)))
                    fm_group.create_dataset(
                        field, data=np.array([mapping[val] for val in column])
                    )
                    fm_group.attrs[f"{field}_mapping"] = json.dumps(mapping)
    finally:
        f.close()


def load_h5(path):
    """Load HDF saved with save_human_understandable function."""
    data = {}

    with h5py.File(path) as h5_file:
        for name, table in h5_file.items():
            table_data = {}
            for key, value in table.items():
                table_data[key] = value[:]

            table_df = pd.DataFrame(table_data)

            for field_key, mapping_str in table.attrs.items():
                field = field_key.split('_')[0]
                mapping = json.loads(mapping_str)
                reverse_mapping = {v: k for k, v in mapping.items()}
                table_df[field] = table_df[field].map(reverse_mapping)

            data[name] = table_df

    return data


def convert_edf():
    """Read an EDF file and write to an HDF file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("edffile", help="The EDF file you would like to parse")
    parser.add_argument("outputfile", help="Where to save the output")
    parser.add_argument(
        "-p",
        "--pandas_hdf",
        action="store_true",
        default=False,
        help="Use pandas to store HDF. Default simplifies HDF strucutre significantly (e.g. map strings to numbers and skip objects)",
    )
    parser.add_argument(
        "-i",
        "--ignore-samples",
        action="store_true",
        default=False,
        help="Should the individual samples be stored in the output? Default is to read samples, ie. ignore-samples=False",
    )
    parser.add_argument(
        "-j",
        "--join",
        action="store_true",
        default=False,
        help="If True events and messages will be joined into one big structure based on the trial number.",
    )
    args = parser.parse_args()
    samples, events, messages = read_edf(args.edffile, ignore_samples=args.ignore_samples)

    if args.join:
        events = trials2events(events, messages)

    if not args.pandas_hdf:
        columns = [
            col
            for col in messages.columns
            if not (messages[col].dtype == np.dtype("O"))
        ]
        messages = messages.loc[:, columns]
        save_human_understandable(samples, events, messages, args.outputfile)
    else:
        events.to_hdf(args.outputfile, "events", mode="w", complevel=9, complib="zlib")
        samples.to_hdf(
            args.outputfile, "samples", mode="w", complevel=9, complib="zlib"
        )
        messages.to_hdf(
            args.outputfile, "messages", mode="w", complevel=9, complib="zlib"
        )
