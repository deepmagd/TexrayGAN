import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.layers import Conv2D, Dense
from models.layers import ResidualLayer, ConvBlock

class Discriminator(Model):
    """ The definition for a network which
        classifies inputs as fake or genuine.
    """
    def __init__(self, img_size, lr, w_init, bn_init):
        """ Initialise a Generator instance.
            TODO: Deal with this parameters and make it more logical
                Arguments:
                img_size : tuple of ints
                    Size of images. E.g. (1, 32, 32) or (3, 64, 64).
        """
        super().__init__()
        self.img_size = img_size

        # Weight Initialisation Parameters
        self.w_init = w_init
        self.bn_init = bn_init

        self.optimiser = tf.keras.optimizers.Adam(lr, beta_1=0.5)

class DiscriminatorStage1(Discriminator):
    """ The definition for a network which
        classifies inputs as fake or genuine.
    """
    def __init__(self, img_size, kernel_size, num_filters, lr, w_init, bn_init):
        """ Initialise a Generator instance.
            TODO: Deal with this parameters and make it more logical
                Arguments:
                img_size : tuple of ints
                    Size of images. E.g. (1, 32, 32) or (3, 64, 64).
                lr : float
        """
        super().__init__(img_size, lr, w_init, bn_init)
        self.d_dim = 64

    def build(self, input_size):
        self.conv_1 = Conv2D(filters=self.d_dim,
                             kernel_size=(4, 4),
                             strides=(2, 2),
                             padding='same',
                             kernel_initializer=self.w_init,
                             use_bias=False
                            )

        self.conv_block_1 = ConvBlock(filters=self.d_dim*2,
                                      kernel_size=(4, 4),
                                      strides=(2, 2),
                                      padding='same',
                                      w_init=self.w_init,
                                      bn_init=self.bn_init,
                                      activation=True
                            )
        self.conv_block_2 = ConvBlock(filters=self.d_dim*4,
                                      kernel_size=(4, 4),
                                      strides=(2, 2),
                                      padding='same',
                                      w_init=self.w_init,
                                      bn_init=self.bn_init,
                                      activation=True
                                    )
        self.conv_block_3 = ConvBlock(filters=self.d_dim*8,
                                      kernel_size=(4, 4),
                                      strides=(2, 2),
                                      padding='same',
                                      w_init=self.w_init,
                                      bn_init=self.bn_init,
                                      activation=False
                                    )

        self.res_block = ResidualLayer(self.d_dim*2, self.d_dim*8, self.w_init, self.bn_init)

        self.dense_embed = Dense(units=128)

        self.conv_block_4 = ConvBlock(
            filters=self.d_dim*8, kernel_size=(1, 1), strides=(1, 1), padding='valid',
            w_init=self.w_init, bn_init=self.bn_init, activation=True
        )

        # (4, 4) == 64/16
        self.conv_2 = Conv2D(
            filters=1, kernel_size=(4, 4), strides=(4, 4), padding="valid",
            kernel_initializer=self.w_init
        )

    def call(self, inputs, training=True):
        images = inputs[0]
        embedding = inputs[1]
        x = self.conv_1(images)
        x = tf.nn.leaky_relu(x, alpha=0.2)

        x = self.conv_block_1(x, training=training)
        x = self.conv_block_2(x, training=training)
        x = self.conv_block_3(x, training=training)

        res = self.res_block(x, training=training)
        x = tf.add(x, res)
        x = tf.nn.leaky_relu(x, alpha=0.2)

        reduced_embedding = self.dense_embed(embedding)
        reduced_embedding = tf.nn.leaky_relu(reduced_embedding, alpha=0.2)
        reduced_embedding = tf.expand_dims(tf.expand_dims(reduced_embedding, 1), 1)
        reduced_embedding = tf.tile(reduced_embedding, [1, 4, 4, 1])
        x = tf.concat([x, reduced_embedding], 3)

        x = self.conv_block_4(x, training=training)
        x = self.conv_2(x)

        return x

    def loss(self, predictions_on_real, predictions_on_wrong, predictions_on_fake):
        """ Calculate the loss for the predictions made on real and fake images.
                Arguments:
                predictions_on_real : Tensor
                predictions_on_fake : Tensor
        """
        real_loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=tf.ones_like(predictions_on_real), logits=predictions_on_real))
        wrong_loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=tf.zeros_like(predictions_on_wrong), logits=predictions_on_wrong))
        fake_loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=tf.zeros_like(predictions_on_fake), logits=predictions_on_fake))
        total_loss = real_loss + (wrong_loss + fake_loss) / 2
        return total_loss


class DiscriminatorStage2(Model):
    """ The definition for a network which
        classifies inputs as fake or genuine.
    """
    def __init__(self, img_size, kernel_size, num_filters):
        """ Initialise a Generator instance.
            TODO: Deal with this parameters and make it more logical
                Arguments:
                img_size : tuple of ints
                    Size of images. E.g. (1, 32, 32) or (3, 64, 64).
        """
        super().__init__()
        pass

    def __call__(self, images, embedding):
        pass

    def loss(self, predictions_on_real, predictions_on_fake):
        pass
