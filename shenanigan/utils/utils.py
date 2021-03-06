from glob import glob
import json
import os
import pickle
import re
import shutil
import tensorflow as tf
from typing import Any, List, Union
import yaml


def format_file_name(image_source_dir: str, file_name: str) -> str:
    """ Format the file name (to make it compatible with windows) and uses
        utf-8 encoding.
    """
    if os.name == "nt":
        # Check to see if running in Windows
        file_name = format_for_windows(file_name)
    return os.path.join(image_source_dir, "{}.jpg".format(file_name)).encode("utf-8")


def read_pickle(path_to_pickle: str) -> Any:
    """ Read a pickle file in latin encoding and return the contents """
    with open(path_to_pickle, "rb") as pickle_file:
        content = pickle.load(pickle_file, encoding="latin1")
    return content


def chunk_list(unchuncked_list, samples_per_shard, end_point):
    """ Split a list up into evenly sized chunks / shards.
        Arguments:
            unchuncked_list: List
                A one-dimensional list
            samples_per_shard: int
                The number of samples to save in a shard
            end_point: int
                The last index that can be equally chunked
    """
    chunked_list = list(chunks(unchuncked_list[:end_point], samples_per_shard))
    chunked_list[-1].extend(unchuncked_list[end_point:])
    return chunked_list


def chunks(unchuncked_list, n):
    """ Yield successive n-sized chunks from a list. """
    for i in range(0, len(unchuncked_list), n):
        yield unchuncked_list[i : i + n]


def get_default_settings(settings_file="settings.yml") -> Any:
    with open(settings_file) as f:
        return yaml.safe_load(f)


def sample_normal(mean: tf.Tensor, log_var: tf.Tensor) -> tf.Tensor:
    """ Use the reparameterization trick to sample a normal distribution.
        Arguments
        mean : Tensor
            Mean of the normal distribution. Shape (batch_size, latent_dim)
        log_var : Tensor
            Diagonal log variance of the normal distribution. Shape (batch_size,
            latent_dim)
    """
    std = tf.math.exp(log_var)
    epsilon = tf.random.normal(
        tf.shape(mean)
    )  # TODO is shape the correct thing to use here?
    return mean + std * epsilon


def kl_loss(mean: tf.Tensor, log_sigma: tf.Tensor):
    loss = -log_sigma + 0.5 * (-1 + tf.math.exp(2.0 * log_sigma) + tf.math.square(mean))
    loss = tf.reduce_mean(loss)
    return loss


def product_list(num_list: List[Union[int, float]]) -> float:
    """ A helper function to simply find the
        product of all elements in the list.
    """
    product = 1
    for dim in num_list:
        product *= dim
    return product


def mkdir(directory: str):
    """ Create directory if it does not exist. """
    try:
        os.makedirs(directory)
    except OSError:
        pass


def remove_file(file_name: str):
    try:
        os.remove(file_name)
    except OSError:
        pass


def rmdir(dir_to_remove: str):
    if os.path.isdir(dir_to_remove):
        shutil.rmtree(dir_to_remove)


def save_options(options, save_dir):
    """ Save all options to JSON file.
        Arguments:
            options: An object from argparse
            save_dir: String location to save the options
    """
    opt_dict = {}
    for option in vars(options):
        opt_dict[option] = getattr(options, option)

    mkdir(save_dir)
    opts_file_path = os.path.join(save_dir, "opts.json")
    with open(opts_file_path, "w") as opt_file:
        json.dump(opt_dict, opt_file)


def format_for_windows(path_string: str) -> str:
    r""" Convert to windows path by replacing `/` with `\` """
    return str(str(path_string).replace("/", "\\"))


def num_tfrecords_in_dir(directory: str) -> int:
    return len(
        [
            name
            for name in os.listdir(directory)
            if os.path.isfile(name) and name.endswith(".tfrecord")
        ]
    )


def normalise(num_list: List[Union[int, float]]) -> List[Union[int, float]]:
    """ Simple normalisation into [0,1] """
    max_x = max(num_list)
    min_x = min(num_list)
    return [(x - min_x) / (max_x - min_x) for x in num_list]


def extract_epoch_num(results_dir: str) -> float:
    candidate_dirs = [
        directory for directory in glob(f"{results_dir}/*/") if "model" in directory
    ]
    if not candidate_dirs:
        raise Exception(f"No candidate models found in '{results_dir}'")
    only_checkpoint_dirs = [
        int(re.search(r"\d+", candidate_dir.split("/")[-2])[0])
        for candidate_dir in candidate_dirs
    ]
    return max(only_checkpoint_dirs)
