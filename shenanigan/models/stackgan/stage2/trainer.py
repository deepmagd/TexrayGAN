import numpy as np
import tensorflow as tf
from tqdm import trange

from shenanigan.trainers import Trainer
from shenanigan.utils.data_helpers import tensors_from_sample


class Stage2Trainer(Trainer):
    """ Trainer which feeds in text as input to the GAN to generate images """

    def __init__(
        self,
        model: tf.keras.Model,
        batch_size: int,
        save_location: str,
        save_every: int,
        save_best_after: int,
        callbacks=None,
        use_pretrained: bool = False,
        show_progress_bar: bool = True,
        **kwargs
    ):
        """ Initialise a model trainer for iamge data.
            Arguments:
            model: models.ConditionalGAN
                The model to train
            batch_size: int
                The number of samples per mini-batch
            save_location: str
                The directory in which to save all
                results from training the model.
        """
        super().__init__(
            model,
            batch_size,
            save_location,
            save_every,
            save_best_after,
            callbacks,
            use_pretrained,
            show_progress_bar,
        )
        self.num_samples = kwargs.get("num_samples")
        self.noise_size = kwargs.get("noise_size")
        self.augment = kwargs.get("augment")
        self.stage_1_generator = kwargs.get("stage_1_generator")

    def train_epoch(self, train_loader: object, epoch_num: int):
        """ Training operations for a single epoch """
        acc_generator_loss = 0
        acc_discriminator_loss = 0
        acc_kl_loss = 0
        acc_disc_real_loss = 0
        acc_disc_wrong_loss = 0
        acc_disc_fake_loss = 0
        text_embedding_size = train_loader.dataset_object.text_embedding_dim
        kwargs = dict(
            desc="Epoch {}".format(epoch_num),
            leave=False,
            disable=not self.show_progress_bar,
        )
        with trange(len(train_loader), **kwargs) as t:
            for batch_idx, sample in enumerate(train_loader.parsed_subset):
                batch_size = len(sample["text"].numpy())
                image_large, wrong_image_large, text_tensor = tensors_from_sample(
                    sample,
                    batch_size,
                    text_embedding_size,
                    self.num_samples,
                    self.augment,
                    img_size="large",
                )

                with tf.GradientTape() as generator_tape, tf.GradientTape() as discriminator_tape:
                    # Forward pass the stage 1 generator to obtain small fake images
                    noise_z = tf.random.normal((batch_size, self.noise_size))
                    fake_images_small, _, _ = self.stage_1_generator(
                        [text_tensor, noise_z], training=False
                    )

                    fake_images_large = self.model.generator(
                        [fake_images_small, text_tensor], training=True
                    )
                    assert (
                        fake_images_large.shape == image_large.shape
                    ), "Real ({}) and fakes ({}) images must have the same dimensions".format(
                        image_large.shape, fake_images_large.shape
                    )

                    real_predictions = self.model.discriminator(
                        [image_large, text_tensor], training=True
                    )
                    wrong_predictions = self.model.discriminator(
                        [wrong_image_large, text_tensor], training=True
                    )
                    fake_predictions = self.model.discriminator(
                        [fake_images_large, text_tensor], training=True
                    )

                    assert (
                        real_predictions.shape
                        == wrong_predictions.shape
                        == fake_predictions.shape
                    ), "Real ({}), wrong ({}) and fake ({}) image predictions must have the same dimensions".format(
                        real_predictions.shape,
                        wrong_predictions.shape,
                        fake_predictions.shape,
                    )

                    generator_loss = self.model.generator.loss(
                        tf.ones_like(fake_predictions), fake_predictions
                    )
                    kl_loss = sum(self.model.generator.losses)
                    generator_loss += kl_loss

                    disc_real_loss = self.model.discriminator.loss(
                        tf.fill(real_predictions.shape, 0.9), real_predictions
                    )
                    disc_wrong_loss = self.model.discriminator.loss(
                        tf.zeros_like(wrong_predictions), wrong_predictions
                    )
                    disc_fake_loss = self.model.discriminator.loss(
                        tf.zeros_like(fake_predictions), fake_predictions
                    )

                    discriminator_loss = (
                        disc_real_loss + 0.5 * disc_wrong_loss + 0.5 * disc_fake_loss
                    )

                # Update gradients
                generator_gradients = generator_tape.gradient(
                    generator_loss, self.model.generator.trainable_variables
                )
                discriminator_gradients = discriminator_tape.gradient(
                    discriminator_loss, self.model.discriminator.trainable_variables
                )

                self.model.generator.optimizer.apply_gradients(
                    zip(generator_gradients, self.model.generator.trainable_variables)
                )
                self.model.discriminator.optimizer.apply_gradients(
                    zip(
                        discriminator_gradients,
                        self.model.discriminator.trainable_variables,
                    )
                )
                # Update tqdm
                t.set_postfix(
                    kl_loss=float(kl_loss),
                    generator_loss=float(generator_loss),
                    discriminator_loss=float(discriminator_loss),
                    disc_real_loss=float(disc_real_loss),
                    disc_wrong_loss=float(disc_wrong_loss),
                    disc_fake_loss=float(disc_fake_loss),
                )
                t.update()

                # Accumulate losses over all samples
                acc_generator_loss += generator_loss
                acc_discriminator_loss += discriminator_loss
                acc_kl_loss += kl_loss
                acc_disc_real_loss += disc_real_loss
                acc_disc_wrong_loss += disc_wrong_loss
                acc_disc_fake_loss += disc_fake_loss

                # if batch_idx == 1:
                #     break

        return {
            "generator_loss": np.asscalar(acc_generator_loss.numpy()) / (batch_idx + 1),
            "discriminator_loss": np.asscalar(acc_discriminator_loss.numpy())
            / (batch_idx + 1),
            "kl_loss": np.asscalar(acc_kl_loss.numpy()) / (batch_idx + 1),
            "discriminator_real_loss": np.asscalar(acc_disc_real_loss.numpy())
            / (batch_idx + 1),
            "discriminator_wrong_loss": np.asscalar(acc_disc_wrong_loss.numpy())
            / (batch_idx + 1),
            "discriminator_fake_loss": np.asscalar(acc_disc_fake_loss.numpy())
            / (batch_idx + 1),
        }

    def val_epoch(self, val_loader: object, epoch_num: int):
        acc_generator_loss = 0
        acc_discriminator_loss = 0
        acc_kl_loss = 0
        acc_disc_real_loss = 0
        acc_disc_wrong_loss = 0
        acc_disc_fake_loss = 0
        text_embedding_size = val_loader.dataset_object.text_embedding_dim
        kwargs = dict(
            desc="Epoch {}".format(epoch_num),
            leave=False,
            disable=not self.show_progress_bar,
        )
        with trange(len(val_loader), **kwargs) as t:
            for batch_idx, sample in enumerate(val_loader.parsed_subset):
                batch_size = len(sample["text"].numpy())
                image_large, wrong_image_large, text_tensor = tensors_from_sample(
                    sample,
                    batch_size,
                    text_embedding_size,
                    self.num_samples,
                    self.augment,
                    img_size="large",
                )
                # Generate fake small images
                noise_z = tf.random.normal((batch_size, self.noise_size))
                fake_images_small, _, _ = self.stage_1_generator(
                    [text_tensor, noise_z], training=False
                )

                fake_images = self.model.generator(
                    [fake_images_small, text_tensor], training=False
                )
                assert (
                    fake_images.shape == image_large.shape
                ), "Real ({}) and fakes ({}) images must have the same dimensions".format(
                    image_large.shape, fake_images.shape
                )

                real_predictions = self.model.discriminator(
                    [image_large, text_tensor], training=False
                )
                wrong_predictions = self.model.discriminator(
                    [wrong_image_large, text_tensor], training=False
                )
                fake_predictions = self.model.discriminator(
                    [fake_images, text_tensor], training=False
                )

                assert (
                    real_predictions.shape
                    == wrong_predictions.shape
                    == fake_predictions.shape
                ), "Real ({}), wrong ({}) and fake ({}) image predictions must have the same dimensions".format(
                    real_predictions.shape,
                    wrong_predictions.shape,
                    fake_predictions.shape,
                )

                generator_loss = self.model.generator.loss(
                    tf.ones_like(fake_predictions), fake_predictions
                )
                kl_loss = sum(self.model.generator.losses)
                generator_loss += kl_loss

                disc_real_loss = self.model.discriminator.loss(
                    tf.ones_like(real_predictions), real_predictions
                )
                disc_wrong_loss = self.model.discriminator.loss(
                    tf.zeros_like(wrong_predictions), wrong_predictions
                )
                disc_fake_loss = self.model.discriminator.loss(
                    tf.zeros_like(fake_predictions), fake_predictions
                )

                discriminator_loss = (
                    disc_real_loss + 0.5 * disc_wrong_loss + 0.5 * disc_fake_loss
                )

                # Update tqdm
                t.set_postfix(
                    kl_loss=float(kl_loss),
                    generator_loss=float(generator_loss),
                    discriminator_loss=float(discriminator_loss),
                    disc_real_loss=float(disc_real_loss),
                    disc_wrong_loss=float(disc_wrong_loss),
                    disc_fake_loss=float(disc_fake_loss),
                )
                t.update()

                # Accumulate losses over all samples
                acc_generator_loss += generator_loss
                acc_discriminator_loss += discriminator_loss
                acc_kl_loss += kl_loss
                acc_disc_real_loss += disc_real_loss
                acc_disc_wrong_loss += disc_wrong_loss
                acc_disc_fake_loss += disc_fake_loss

                # if batch_idx == 1:
                #     break

        return {
            "generator_loss": np.asscalar(acc_generator_loss.numpy()) / (batch_idx + 1),
            "discriminator_loss": np.asscalar(acc_discriminator_loss.numpy())
            / (batch_idx + 1),
            "kl_loss": np.asscalar(acc_kl_loss.numpy()) / (batch_idx + 1),
            "discriminator_real_loss": np.asscalar(acc_disc_real_loss.numpy())
            / (batch_idx + 1),
            "discriminator_wrong_loss": np.asscalar(acc_disc_wrong_loss.numpy())
            / (batch_idx + 1),
            "discriminator_fake_loss": np.asscalar(acc_disc_fake_loss.numpy())
            / (batch_idx + 1),
        }
