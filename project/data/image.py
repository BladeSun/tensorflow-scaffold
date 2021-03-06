"""Estimator inputs definitions. """
from typing import Tuple
import tensorflow as tf


def read_image(image_data: tf.Tensor, augment: bool, image_size: Tuple[int, int]=(224, 224),
               data_is_path: bool=False) -> tf.Tensor:
    """
    Decodes images from file contents, random flips, resizes and normalizes them.

    :param image_data: The JPEG bytes to decode.
    :param data_is_path: If set, the data is treated as a path to an image file. If unset, data is considered raw bytes.
    :param augment: Is set, images are augmented by random cropping.
    :param image_size: The image size to resize the images to.
    :return: The decoded image.
    """

    if data_is_path:
        image_data = tf.gfile.FastGFile(image_data, 'rb').read()

    if augment:
        with tf.variable_scope('read_image_cropped'):
            # Extract image shape from raw JPEG image buffer.
            image_shape = tf.image.extract_jpeg_shape(image_data)

            # Get a crop window with distorted bounding box.
            full_image = tf.constant([[0, 0, 1., 1.]], dtype=tf.float32, shape=[1, 1, 4])
            sample_distorted_bounding_box = tf.image.sample_distorted_bounding_box(image_shape,
                                                                                   max_attempts=10,
                                                                                   bounding_boxes=full_image,
                                                                                   use_image_if_no_bounding_boxes=True,
                                                                                   aspect_ratio_range=[.5, 1.5],
                                                                                   area_range=[.5, 1.])  # TODO: Extract magic numbers
            bbox_begin, bbox_size, distort_bbox = sample_distorted_bounding_box

            # Decode and crop image.
            offset_y, offset_x, _ = tf.unstack(bbox_begin)
            target_height, target_width, _ = tf.unstack(bbox_size)
            crop_window = tf.stack([offset_y, offset_x, target_height, target_width])
            image = tf.image.decode_and_crop_jpeg(image_data, crop_window, channels=3,
                                                  try_recover_truncated=True, acceptable_fraction=.8,
                                                  name='decode_image')
    else:
        with tf.variable_scope('read_image'):
            # NOTE: decode_image not return the image's shape, however decode_jpeg also decodes PNG files.
            #       https://github.com/tensorflow/tensorflow/issues/9356
            image = tf.image.decode_jpeg(image_data, channels=3,
                                         try_recover_truncated=True, acceptable_fraction=.8,
                                         name='decode_image')

    with tf.variable_scope('convert_image'):
        # Convert to floating-point.
        image = tf.image.convert_image_dtype(image, dtype=tf.float32, name='convert_image_dtype')

    with tf.variable_scope('resize_and_normalize'):
        # We need to get the image to a known size.
        images = tf.expand_dims(image, axis=0, name='expand_image_dims')
        images = tf.image.resize_images(images, size=image_size, method=tf.image.ResizeMethod.BICUBIC)  # TODO: Do in batch?

        # Note: tf.squeeze implicitly converts to tf.float32. For convert_to_image_type we
        # expect uint8 as otherwise the values won't be scaled.
        image = tf.squeeze(images, axis=0, name='squeeze_image_dims')

    return image


def augment_image(image: tf.Tensor, fast_mode: bool=True) -> tf.Tensor:
    """
    Augments an image randomly.

    :param image: The image.
    :param fast_mode: When set, not all color distortions are being used.
    :return: The augmented image.
    """
    with tf.variable_scope('distort_colors'):
        image = tf.image.random_flip_left_right(image)
        # image = tf.image.random_flip_up_down(image)
        image = tf.image.random_saturation(image, lower=.5, upper=1.5)
        image = tf.image.random_brightness(image, max_delta=0.125)

        # These operations apparently are slower.
        if not fast_mode:
            image = tf.image.random_hue(image, max_delta=0.2)
            image = tf.image.random_contrast(image, lower=0.5, upper=1.5)

    return image


def parse_tfexample(ex: tf.train.Example):
    # This function parses a TFRecord file for Examples. In order to use
    # SequenceExamples, see https://www.tensorflow.org/api_docs/python/tf/parse_single_sequence_example
    # In order to decode a raw byte sequence, see https://www.tensorflow.org/api_docs/python/tf/decode_raw
    features = {
        'image/class/label': tf.FixedLenFeature([], dtype=tf.int64),
        'image/encoded': tf.FixedLenFeature([], dtype=tf.string),
        # 'image/format': tf.FixedLenFeature([], dtype=tf.string),
        # 'image/height': tf.FixedLenFeature([], dtype=tf.int64),
        # 'image/width': tf.FixedLenFeature([], dtype=tf.int64),
    }
    parsed = tf.parse_single_example(ex, features)
    return parsed['image/encoded'], parsed['image/class/label']
