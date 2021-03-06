# SIPEC
# MARKUS MARKS
# SEGMENTATION PART
# This code is optimized from the Mask RCNN (Waleed Abdulla, (c) 2017 Matterport, Inc.) repository


import gc
import random
from joblib import Parallel, delayed


from argparse import ArgumentParser
import os
import numpy as np

import imgaug.augmenters as iaa

## adapted from matterport Mask_RCNN implementation
from SwissKnife.mrcnn.config import Config
import SwissKnife.mrcnn.model as modellib
from SwissKnife.mrcnn import utils

from SwissKnife.utils import (
    setGPU,
    check_folder,
    save_dict,
    maskedImg,
    set_random_seed,
    clearMemory,
)

# TODO: fix this import bug here
from SwissKnife.dataprep import get_segmentation_data


# TODO: include validation image that network detects new Ground truth!!
def mold_image(img, config=None, dimension=None):
    if config:
        image, window, scale, padding, crop = utils.resize_image(
            img[:, :, :],
            min_dim=config.IMAGE_MIN_DIM,
            min_scale=config.IMAGE_MIN_SCALE,
            max_dim=config.IMAGE_MAX_DIM,
            mode=config.IMAGE_RESIZE_MODE,
        )
    elif dimension:
        image, window, scale, padding, crop = utils.resize_image(
            img[:, :, :], min_dim=dimension, max_dim=dimension, mode="square",
        )
    else:
        return NotImplementedError
    return image


def mold_video(video, dimension, n_jobs=40):
    results = Parallel(
        n_jobs=n_jobs, max_nbytes=None, backend="multiprocessing", verbose=40
    )(delayed(mold_image)(image, dimension=dimension) for image in video)
    return results


# TODO: batch size in inference
class PrimateConfig(Config):
    NAME = "primate"
    GPU_COUNT = 1
    IMAGES_PER_GPU = 2
    BATCH_SIZE = 2
    BACKBONE = "resnet101"
    MAX_GT_INSTANCES = 4
    DETECTION_MAX_INSTANCES = 10
    NUM_CLASSES = 2
    STEPS_PER_EPOCH = 100
    DETECTION_MIN_CONFIDENCE = 0.85
    LEARNING_RATE = 0.0025
    USE_MINI_MASK = True
    MINI_MASK_SHAPE = (56, 56)

    IMAGE_RESIZE_MODE = "crop"
    IMAGE_MIN_DIM = 1280
    IMAGE_MAX_DIM = 1280
    IMAGE_SHAPE = [1280, 1280, 3]

    TRAIN_ROIS_PER_IMAGE = 200
    WEIGHT_DECAY = 0.0001

    GRADIENT_CLIP_NORM = 1.0


class InferenceConfigPrimate(PrimateConfig):
    IMAGE_RESIZE_MODE = "square"
    IMAGES_PER_GPU = 1
    BATCH_SIZE = 1

    DETECTION_MIN_CONFIDENCE = 0.8
    IMAGE_MIN_DIM = 1920
    IMAGE_MAX_DIM = 1920
    IMAGE_SHAPE = [1920, 1920, 3]
    # DETECTION_MIN_CONFIDENCE = 0.99
    # IMAGE_MIN_DIM = 4096
    # IMAGE_MAX_DIM = 4096
    # IMAGE_SHAPE = [4096, 4096, 3]


class MouseConfig(Config):
    NAME = "mouse"
    BACKBONE = "resnet101"
    IMAGES_PER_GPU = 1
    BATCH_SIZE = 1
    NUM_CLASSES = 2
    STEPS_PER_EPOCH = 100
    DETECTION_MIN_CONFIDENCE = 0.9
    GPU_COUNT = 1

    LEARNING_RATE = 0.001
    IMAGE_RESIZE_MODE = "square"
    IMAGE_MIN_DIM = 1024
    IMAGE_MAX_DIM = 1024
    IMAGE_SHAPE = [1024, 1024, 3]
    USE_MINI_MASK = True
    MINI_MASK_SHAPE = (56, 56)
    MAX_GT_INSTANCES = 4
    TRAIN_ROIS_PER_IMAGE = 128

    WEIGHT_DECAY = 0.0001
    GRADIENT_CLIP_NORM = 1.0


class InferenceConfigMouse(MouseConfig):
    # TODO: test / anpassen
    DETECTION_MIN_CONFIDENCE = 0.9
    IMAGES_PER_GPU = 1
    BATCH_SIZE = 1


class IneichenConfig(Config):
    NAME = "mouse"
    BATCH_SIZE = 1
    IMAGES_PER_GPU = 1
    NUM_CLASSES = 2
    STEPS_PER_EPOCH = 100
    DETECTION_MIN_CONFIDENCE = 0.95
    GPU_COUNT = 1

    IMAGE_RESIZE_MODE = "square"
    IMAGE_MIN_DIM = 320
    IMAGE_MAX_DIM = 320
    # TRAIN_BN = True
    MINI_MASK_SHAPE = (56, 56)


class InferencIneichenConfig(IneichenConfig):
    DETECTION_MIN_CONFIDENCE = 0.99
    IMAGES_PER_GPU = 1
    BATCH_SIZE = 1


class MaskFilter:
    def __init__(self):
        pass

    def train(self):
        pass

    def predict(self):
        pass


class SegModel:
    def __init__(self, species):
        self.species = species
        if self.species == "mouse":
            self.config = MouseConfig()
        if self.species == "primate" or self.species == "jin":
            self.config = PrimateConfig()
        if self.species == "ineichen":
            self.config = IneichenConfig()
        self.model_path = None
        self.augmentation = None
        self.model = None

        if self.species == "mouse":
            self.inference_config = InferenceConfigMouse()

        if self.species == "primate":
            self.inference_config = InferenceConfigPrimate()

        if self.species == "ineichen":
            self.inference_config = InferencIneichenConfig()

        if self.species == "jin":
            self.inference_config = InferencJinConfig()

        pass

    def train(self, dataset_train, dataset_val):
        if self.species == "primate":
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=3,
                layers="heads",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=5,
                layers="5+",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=8,
                layers="4+",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=10,
                layers="3+",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                # learning_rate=self.config.LEARNING_RATE / 25,
                learning_rate=self.config.LEARNING_RATE / 5,
                # epochs=10,
                epochs=60,
                layers="all",
                augmentation=self.augmentation,
            )

            self.model.train(
                dataset_train,
                dataset_val,
                # learning_rate=self.config.LEARNING_RATE / 25,
                learning_rate=self.config.LEARNING_RATE / 10,
                # epochs=10,
                epochs=100,
                layers="all",
                augmentation=self.augmentation,
            )
        ###

        #  mouse
        if self.species == "mouse" or self.species == "ineichen":
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                # epochs=1,
                epochs=3,
                layers="heads",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=5,
                layers="5+",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=8,
                layers="4+",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                epochs=10,
                layers="3+",
                augmentation=self.augmentation,
            )
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE / 5,
                # epochs=1,
                epochs=100,
                layers="all",
                augmentation=self.augmentation,
            )

        if self.species == "test":
            self.model.train(
                dataset_train,
                dataset_val,
                learning_rate=self.config.LEARNING_RATE,
                # epochs=1,
                epochs=1,
                layers="heads",
                augmentation=self.augmentation,
            )

    def init_augmentation(self):

        if self.species == "mouse" or self.species == "ineichen":
            sometimes = lambda aug: iaa.Sometimes(0.5, aug)
            self.augmentation = iaa.Sequential(
                [
                    # apply the following augmenters to most images
                    #             iaa.Fliplr(0.5), # horizontally flip 50% of all images\
                    # crop images by -5% to 10% of their height/width
                    sometimes(
                        iaa.Affine(
                            # #                 scale={("x": (0.75, 1.25), "y": (0.75, 1.25))}, # scale images to 80-120% of their size, individually per axis
                            scale=(
                                0.9,
                                1.1,
                            ),  # scale images to 80-120% of their size, individually per axis
                            #                 #                 translate_percent={"x": (-0.1, 0.1), "y": (-0.2, 0.2)}, # translate by -20 to +20 percent (per axis)
                            rotate=(-90, 90),  # rotate by -45 to +45 degrees
                            shear=(-10, 10),  # shear by -16 to +16 degrees
                            #                 order=[0, 1], # use nearest neighbour or bilinear interpolation (fast)
                            #                 cval=0, # if mode is constant, use a cval between 0 and 255
                            #                 mode=ia.ALL # use any of scikit-image's warping modes (see 2nd image from the top for examples)
                        )
                    ),
                    sometimes(
                        iaa.CoarseDropout(p=0.2, size_percent=0.8, per_channel=False)
                    ),
                    sometimes(
                        iaa.CoarseDropout(p=0.05, size_percent=0.25, per_channel=False)
                    ),
                    sometimes(iaa.GaussianBlur(sigma=(0, 0.5))),
                ],
                random_order=True,
            )

        if self.species == "primate" or self.species == "jin":
            sometimes = lambda aug: iaa.Sometimes(0.2, aug)  # latest run 0.2

            self.augmentation = iaa.Sequential(
                [
                    sometimes(
                        iaa.CoarseDropout(p=0.1, size_percent=0.02, per_channel=False)
                    ),
                    sometimes(
                        iaa.CoarseDropout(p=0.1, size_percent=0.2, per_channel=False)
                    ),
                    sometimes(
                        iaa.CoarseDropout(p=0.1, size_percent=0.8, per_channel=False)
                    ),
                ],
                random_order=True,
            )

    def init_training(self, model_path, init_with="coco"):
        self.model_path = model_path
        # Create model in training mode
        self.model = modellib.MaskRCNN(
            mode="training", config=self.config, model_dir=self.model_path
        )

        self.config.display()

        if init_with == "imagenet":
            self.model.load_weights(self.model.get_imagenet_weights(), by_name=True)
        elif init_with == "coco":
            # Load weights trained on MS COCO, but skip layers that
            # are different due to the different number of classes
            # See README for instructions to download the COCO weights
            COCO_MODEL_PATH = os.path.join("./", "mask_rcnn_coco.h5")
            if not os.path.exists(COCO_MODEL_PATH):
                utils.download_trained_weights(COCO_MODEL_PATH)
            self.model.load_weights(
                COCO_MODEL_PATH,
                by_name=True,
                exclude=[
                    "mrcnn_class_logits",
                    "mrcnn_bbox_fc",
                    "mrcnn_bbox",
                    "mrcnn_mask",
                ],
            )
        elif init_with == "last":
            # Load the last model you trained and continue training
            # self.model.load_weights(self.model.find_last(), by_name=True)
            self.model.load_weights(
                "/media/nexus/storage4/swissknife_results/segmentation/mouse_/mouse20200624T0724/mask_rcnn_mouse_0040.h5",
                by_name=True,
            )

    def set_inference(self, model_path=None):
        # FIXME: remove hardcoing

        # functioning primate model
        # path = '/home/nexus/mask_rcnn_primate_0119.h5'

        if "mask_rcnn" in model_path:
            helper_path = model_path.split("mask_rcnn")[0]
            self.model = modellib.MaskRCNN(
                mode="inference", config=self.inference_config, model_dir=helper_path
            )
        elif "mask_rcnn" not in model_path:
            self.model = modellib.MaskRCNN(
                mode="inference", config=self.inference_config, model_dir=model_path
            )
            model_path = self.model.find_last()
        else:
            return NotImplementedError

        # Recreate the model in inference mode
        self.model.load_weights(model_path, by_name=True)
        return model_path

    def evaluate(self, dataset_val, maskfilter=None):

        image_ids = dataset_val.image_ids

        APs = []
        for image_id in image_ids:
            # Load image and ground truth data
            image, image_meta, gt_class_id, gt_bbox, gt_mask = modellib.load_image_gt(
                dataset_val, self.inference_config, image_id, use_mini_mask=False
            )
            r = self.detect_image_original(image, verbose=0)
            if maskfilter:
                r = maskfilter.predict(r)
            # Compute AP
            AP, precisions, recalls, overlaps = utils.compute_ap(
                gt_bbox,
                gt_class_id,
                gt_mask,
                r["rois"],
                r["class_ids"],
                r["scores"],
                r["masks"],
            )
            APs.append(AP)

        mean_ap = np.mean(APs)
        print("evaluation done")
        print("mAP: ", mean_ap)

        return mean_ap

    def detect_image(self, img, mold=True, verbose=1):
        if mold:
            # img = mold_image(img, self.inference_config, dimension=2048)
            img = mold_image(img, self.inference_config, dimension=1024)
        result = self.model.detect([img], verbose=verbose)
        return img, result[0]["masks"], result[0]["rois"], result[0]["scores"]

    def detect_image_original(self, img, mold=True, verbose=1):
        if mold:
            img = mold_image(img, self.inference_config)
        result = self.model.detect([img], verbose=verbose)
        return result[0]

    def detect_video(self, video, results_sink=None):

        videodata = mold_video(video, self.inference_config)

        results = []
        batch_size = self.inference_config.BATCH_SIZE
        batches = int(len(videodata) / batch_size)
        from time import time

        for idx, batch in enumerate(range(batches)):
            start = time()
            data = videodata[idx * batch_size : (idx + 1) * batch_size]
            vid_results = self.model.detect(data, verbose=1)
            results = results + vid_results
            print("time", time() - start)

        if results_sink:
            check_folder(results_sink)
            save_dict(results_sink + "SegResults.pkl", results)
        else:
            return results


def evaluate_network(model_path, species, filter_masks=False, cv_folds=0):
    # load training and val data
    mean_aps = []
    for fold in range(cv_folds + 1):
        dataset_train, dataset_val = get_segmentation_data(
            species, cv_folds=cv_folds, fold=fold, fraction=1.0
        )
        model = SegModel(species)
        model.set_inference(model_path=model_path)
        if filter_masks:
            maskfilter = MaskFilter()
            maskfilter.train(dataset_train)
            mean_ap = model.evaluate(dataset_val, maskfilter=maskfilter)
        else:
            mean_ap = model.evaluate(dataset_val)
        print("MEAN AP", mean_ap)
        mean_aps.append(mean_ap)
    print("overall aps", mean_aps)
    print("mAP: ", str(np.mean(np.array(mean_aps))))


def train_on_data_once(model_path, species, cv_folds, fold=0, fraction=None, debug=0):
    # load training and val data
    # dataset_train, dataset_val = get_segmentation_data(
    #     species, cv_folds=cv_folds, fold=fold, fraction=fraction
    # )
    dataset_train, dataset_val = get_segmentation_data(
        "mouse", cv_folds=cv_folds, fold=fold, fraction=fraction
    )
    # initiate mouse model
    model = SegModel(species)
    # initiate training
    model.init_training(model_path=model_path, init_with="last")
    model.init_augmentation()
    # start training
    print("training on #NUM images : ", str(len(dataset_train.image_ids)))
    model.train(dataset_train, dataset_val)
    # evaluate model
    model = SegModel(species)
    model_path = model.set_inference(model_path=model_path)
    mean_ap = model.evaluate(dataset_val)

    # if species == "primate" or species == "mouse":
    #     debug = 1
    if debug:
        helper = model_path.split("mask_rcnn_primate_0")
        epochs = [
            "010",
            "020",
            "030",
        ]
        print(helper)
        print(helper[0] + "mask_rcnn_primate_0" + "001" + ".h5")
        for epoch in epochs:
            model = SegModel("primate")
            model.set_inference(
                model_path=helper[0] + "mask_rcnn_primate_0" + epoch + ".h5"
            )
            mean_ap = model.evaluate(dataset_val)
            print(epoch)
            print(mean_ap)

    return model, mean_ap


def do_ablation(species, cv_folds, random_seed, fraction):
    experiment_name = "ablation"

    import os.path

    results_path = "./segmentation_logs/" + species + "_" + experiment_name + "/"
    results_fname = (
        results_path
        + "./results_array"
        + "_"
        + str(random_seed)
        + "_"
        + str(fraction)
        + ".npy"
    )
    if os.path.isfile(results_fname):
        results = list(np.load(results_fname, allow_pickle=True))
    else:
        results = [["random_seed", "data_fraction", "MEAN_AP"]]

    set_random_seed(random_seed)
    random.seed(random_seed)

    mean_aps = train_on_data(
        species,
        cv_folds=cv_folds,
        fraction=fraction,
        to_file=False,
        experiment=experiment_name,
    )
    results.append([random_seed, fraction, mean_aps])
    # check_folder(results_path)
    np.save(results_fname, results, allow_pickle=True)


def train_on_data(
    species, cv_folds, fraction=None, to_file=True, experiment="", fold=None
):
    # path, where to save trained model
    model_path = (
        "/media/nexus/storage5/swissknife_results/segmentation/"
        + species
        + "_"
        + experiment
        + "/"
    )
    model = None
    mean_aps = []
    if cv_folds > 0:
        if fold is not None:
            print("TRAINING on FOLD", str(fold))
            model, mean_ap = train_on_data_once(
                model_path, species, cv_folds=cv_folds, fold=fold, fraction=fraction
            )
            mean_aps.append(mean_ap)
            gc.collect()
        else:
            for fold in range(cv_folds):
                model, mean_ap = train_on_data_once(
                    model_path, species, cv_folds=cv_folds, fold=fold, fraction=fraction
                )
                mean_aps.append(mean_ap)
                gc.collect()
    else:
        model, mean_ap = train_on_data_once(
            model_path, species, cv_folds=cv_folds, fold=0, fraction=fraction
        )
        print("MEAN AP", mean_ap)

    if to_file:
        if fold is not None:
            fold = str(fold)
        else:
            fold = ""
        experiment_name = "cv"
        import os.path

        results_path = "./segmentation_logs/" + species + "_" + experiment_name + "/"
        results_fname = (
            results_path
            + "./results_array"
            + "_"
            + str(0)
            + "_"
            + str(fraction)
            + "_fold_"
            + fold
            + ".npy"
        )
        if os.path.isfile(results_fname):
            results = list(np.load(results_fname, allow_pickle=True))
        else:
            results = [["random_seed", "data_fraction", "MEAN_AP"]]

        results.append([0, fraction, mean_aps])
        check_folder(results_path)
        np.save(results_fname, results, allow_pickle=True)

    return mean_aps


def main():
    args = parser.parse_args()
    operation = args.operation
    gpu_name = args.gpu
    cv_folds = args.cv_folds
    random_seed = args.random_seed
    fraction = args.fraction
    model_path = args.model_path
    fold = args.fold

    from keras import backend as K

    if gpu_name is not None:
        setGPU(K, gpu_name)

    if operation == "train_primate":
        # TODO: fix having random seed here as global argument
        # TODO: shorten everything
        set_random_seed(random_seed)
        random.seed(random_seed)
        train_on_data(
            species="primate",
            cv_folds=cv_folds,
            to_file=True,
            fold=fold,
            fraction=fraction,
        )
    if operation == "train_mouse":
        set_random_seed(random_seed)
        random.seed(random_seed)
        train_on_data(
            species="mouse",
            cv_folds=cv_folds,
            to_file=True,
            fold=fold,
            fraction=fraction,
        )
    if operation == "mouse_ablation":
        do_ablation(
            species="mouse",
            cv_folds=cv_folds,
            random_seed=random_seed,
            fraction=fraction,
        )
    if operation == "ineichen":
        train_on_data(species="ineichen")
    if operation == "jin":
        train_on_data(species="jin")
    if operation == "inference_primate":
        inference_on_multi_animal_videos(species="primate")
    if operation == "evaluate_network":
        evaluate_network(model_path, "primate", cv_folds=5)
    # TODO: pass video
    if operation == "inference_mouse":
        inference_for_single_mouse_videos()

    print("done")


parser = ArgumentParser()
parser.add_argument(
    "--cv_folds",
    action="store",
    dest="cv_folds",
    type=int,
    default=0,
    help="folds for cross validation",
)
parser.add_argument(
    "--operation",
    action="store",
    dest="operation",
    type=str,
    default="train_primate",
    help="standard training options for SIPEC data",
)
parser.add_argument(
    "--gpu",
    action="store",
    dest="gpu",
    type=str,
    default=None,
    help="filename of the video to be processed (has to be a segmented one)",
)

parser.add_argument(
    "--random_seed",
    action="store",
    dest="random_seed",
    type=int,
    default=None,
    help="random seed for this experiment",
)

parser.add_argument(
    "--fraction",
    action="store",
    dest="fraction",
    type=float,
    default=None,
    help="fraction to use for training",
)

parser.add_argument(
    "--model_path",
    action="store",
    dest="model_path",
    type=str,
    default=None,
    help="model path for evaluation",
)

parser.add_argument(
    "--fold",
    action="store",
    dest="fold",
    type=int,
    default=None,
    help="fold for crossvalidation",
)

if __name__ == "__main__":
    main()
