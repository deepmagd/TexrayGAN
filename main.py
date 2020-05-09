import argparse
import os
import sys

import numpy as np
import tensorflow as tf

from dataloaders.dataloaders import create_dataloaders
from models.conditional_gans import StackGAN1, StackGAN2
from trainers.trainers import get_trainer
from utils.callbacks import LearningRateDecay
from utils.datasets import DATASETS
from utils.logger import LogPlotter
from utils.utils import extract_epoch_num, get_default_settings, save_options
from visualise.visualise import compare_generated_to_real

SETTINGS_FILE = 'settings.yaml'
RESULTS_ROOT = 'results'
SEED = 1234

tf.random.set_seed(SEED)
np.random.seed(SEED)

def parse_arguments(args_to_parse):
    """ Parse CLI arguments """
    default_settings = get_default_settings(SETTINGS_FILE)

    descr = 'Tensorflow 2 implementation of StackGAN for generating x-ray images'
    parser = argparse.ArgumentParser(description=descr)

    general = parser.add_argument_group('General settings')
    general.add_argument(
        'name', type=str, help="The name of the model - used for saving and loading."
    )
    general.add_argument(
        '-d', '--dataset-name', help="Name of the dataset to use during training.",
        default=default_settings['dataset'], choices=DATASETS
    )
    general.add_argument(
        '--save-every', type=int, default=default_settings['save_every_n_epochs'],
        help='Save the model every n epochs, regardless of the validation loss'
    )
    general.add_argument(
        '--stage', type=int, choices=[1, 2], required=True,
        help='Whether to train stage 1 or 2.'
    )

    data = parser.add_argument_group('Data settings')
    data.add_argument(
        '--samples-per-shard', type=int, default=default_settings['samples_per_shard'],
        help="The number of samples to save in each TFRecord shard."
    )

    training = parser.add_argument_group('Training settings')
    training.add_argument(
        '-e', '--num-epochs', type=int, default=default_settings['num_epochs'],
        help='Maximum number of epochs to run for.'
    )
    training.add_argument(
        '-b', '--batch-size', type=int, default=default_settings['batch_size'],
        help='The number of images to use in a batch during training'
    )
    training.add_argument(
        '-k', '--kernel-size', type=int, default=default_settings['kernel_size'],
        help='Integer which indicates the size of the kernel. \
              E.g. --kernel-size = 4 results in a (4, 4) kernel'
    )
    training.add_argument(
        '-f', '--num-filters', type=int, default=default_settings['num_filters'],
        help='The number of filters to stack.'
    )
    training.add_argument(
        '--lr_g', type=float, default=default_settings['learning_rate_g'],
        help='Generator learning rate.'
    )
    training.add_argument(
        '--lr_d', type=float, default=default_settings['learning_rate_d'],
        help='Discriminator learning rate.'
    )
    training.add_argument(
        '--conditional-emb-size', type=int, help='The number of elements in the conditiona embedding',
        default=default_settings['conditional_emb_size']
    )
    training.add_argument(
        '-s', '--target-size', type=int, default=default_settings['target_size'],
        help='The target dimension for the training data. \
              E.g. --target-size = 256 results in a (256, 256) image'
    )

    evaluation = parser.add_argument_group('Evaluation settings')
    evaluation.add_argument(
        '--use-pretrained', action='store_true', default=False,
        help='Load a pretrained model for inference'
    )
    evaluation.add_argument(
        '--epoch-num', type=int, default=default_settings['epoch_num'],
        help='Which checkpointed epoch number to load into memory. If set to -1, then load the most recent.'
    )

    visualisation = parser.add_argument_group('Visualisation settings')
    visualisation.add_argument(
        '--visualise', action='store_true', default=False,
        help='Run visualisations after loading / training the model'
    )
    visualisation.add_argument(
        '-i', '--images-to-generate', type=int, default=default_settings['num_images_to_generate'],
        help='The number of images to generate and visualise.'
    )
    visualisation.add_argument(
        '-c', '--images-to-classify', type=int, default=default_settings['num_images_to_classify'],
        help='The number of images to classify and visualise.'
    )

    args = parser.parse_args(args_to_parse)
    args.kernel_size = (args.kernel_size, args.kernel_size)
    return args

def load_model(args, image_dims, results_dir):
    model = StackGAN1(
        img_size=image_dims,
        kernel_size=args.kernel_size,
        num_filters=args.num_filters,
        reshape_dims=[args.target_size, args.target_size, args.num_filters],
        lr_g=args.lr_g,
        lr_d=args.lr_d,
        conditional_emb_size=args.conditional_emb_size,
        w_init=tf.random_normal_initializer(stddev=0.02),
        bn_init=tf.random_normal_initializer(1., 0.02)
    )
    if args.stage == 2:
        results_dir = results_dir.replace('stage-2', 'stage-1')

    if args.epoch_num == -1:
        # Find last checkpoint
        args.epoch_num = extract_epoch_num(results_dir)

    pretrained_dir = os.path.join(results_dir, f'model_{args.epoch_num}')
    model.generator = tf.saved_model.load(os.path.join(pretrained_dir, 'generator', 'generator'))
    model.discriminator = tf.saved_model.load(os.path.join(pretrained_dir, 'discriminator', 'discriminator'))
    return model

def main(args):
    results_dir = os.path.join(RESULTS_ROOT, args.name, f'stage-{args.stage}')
    save_options(options=args, save_dir=results_dir)

    default_settings = get_default_settings(SETTINGS_FILE)

    train_loader, val_loader, small_image_dims, large_image_dims = create_dataloaders(args)

    lr_decay = LearningRateDecay(
        decay_factor=default_settings['callbacks']['learning_rate_decay']['decay_factor'],
        every_n=default_settings['callbacks']['learning_rate_decay']['every_n']
    )

    # Create the model
    if args.stage == 1 and args.use_pretrained:
        model = load_model(args, small_image_dims, results_dir)

    elif args.stage == 1:
        model = StackGAN1(
            img_size=small_image_dims,
            kernel_size=args.kernel_size,
            num_filters=args.num_filters,
            reshape_dims=[args.target_size, args.target_size, args.num_filters],
            lr_g=args.lr_g,
            lr_d=args.lr_d,
            conditional_emb_size=args.conditional_emb_size,
            w_init=tf.random_normal_initializer(stddev=0.02),
            bn_init=tf.random_normal_initializer(1., 0.02)
        )

        trainer_class = get_trainer(args.stage)
        trainer = trainer_class(
            model=model,
            batch_size=args.batch_size,
            save_location=results_dir,
            save_every=args.save_every,
            save_best_after=default_settings['save_best_after_n_epochs'],
            callbacks=[lr_decay],
            num_embeddings=default_settings['num_embeddings'],
            num_samples=default_settings['num_samples'],
            noise_size=default_settings['noise_size'],
            augment=default_settings['augment']
        )
        trainer(train_loader, val_loader, num_epochs=args.num_epochs)

        # Plot metrics
        plotter = LogPlotter(results_dir)
        plotter.learning_curve()

    elif args.stage == 2 and args.use_pretrained:
        raise NotImplementedError('We have not yet provided the ability to load pretrained stage 2 models')

    elif args.stage == 2:
        model_stage2 = StackGAN2(
            img_size=small_image_dims,
            kernel_size=args.kernel_size,
            num_filters=args.num_filters,
            reshape_dims=[args.target_size, args.target_size, args.num_filters],
            lr_g=args.lr_g,
            lr_d=args.lr_d,
            conditional_emb_size=args.conditional_emb_size,
            w_init=tf.random_normal_initializer(stddev=0.02),
            bn_init=tf.random_normal_initializer(1., 0.02)
        )
        model_stage1 = load_model(args, small_image_dims, results_dir)

        trainer_class = get_trainer(args.stage)
        trainer = trainer_class(
            model=model_stage2,
            batch_size=args.batch_size,
            save_location=results_dir,
            save_every=args.save_every,
            save_best_after=default_settings['save_best_after_n_epochs'],
            callbacks=[lr_decay],
            num_embeddings=default_settings['num_embeddings'],
            num_samples=default_settings['num_samples'],
            noise_size=default_settings['noise_size'],
            augment=default_settings['augment'],
            stage_1_generator=model_stage1.generator
        )
        trainer(train_loader, val_loader, num_epochs=args.num_epochs)

        # Plot metrics
        plotter = LogPlotter(results_dir)
        plotter.learning_curve()

    if args.visualise:
        # TODO: Check if the model is in eval mode
        # Visualise fake images from training set
        compare_generated_to_real(
            dataloader=train_loader,
            num_images=args.images_to_generate,
            noise_size=default_settings['noise_size'],
            model=model,
            save_location=os.path.join(results_dir, 'viz')
        )


if __name__ == '__main__':
    args = parse_arguments(sys.argv[1:])
    main(args)
