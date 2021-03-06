# SIPEC
# MARKUS MARKS
# COMPARISON OF DLC VS. END-TO-END

from skimage.color import rgb2gray
from skimage.util import img_as_uint

from tqdm import tqdm
from argparse import ArgumentParser
import json
import pickle
import numpy as np
from glob import glob
from time import time
import pandas as pd
from imgaug import augmenters as iaa

import tensorflow as tf
from keras import backend as K

from SwissKnife.datasets.mouse import MouseDataset
from SwissKnife.architectures import (
    dlc_model,
    classification_small,
    recurrent_model_tcn,
    pretrained_recognition,
    dlc_model_sturman,
)
from SwissKnife.utils import (
    Metrics,
    train_model,
    eval_model,
    pathForFile,
    load_config,
    check_directory,
    setGPU,
    get_optimizer,
    get_callbacks,
    set_random_seed,
    save_dict,
    load_dict,
)
from SwissKnife.dataloader import Dataloader


def run_experiment(
    base_path, config, num_classes=4, results_sink="", continuation=0, fraction=None
):
    # TODO: replace stuff
    # old path
    videos = glob(base_path + "/inference/segmentation/individual/*.npy")
    dlc_annot = glob(base_path + "/dlc_annotations/*.npy")
    labels = glob(base_path + "/labels/" + config["experimenter"] + "/*.npy")

    _results_sink = results_sink

    crop = 15000

    test_videos = labels[:]
    if continuation:
        results_dict = load_dict(_results_sink + "results_dict" + ".npy")
        results_array = np.load(_results_sink + "results_array" + ".npy")
        already_processed = np.unique(results_array[:, 1])
        results_array = list(results_array)
    else:
        results_dict = {}
        results_array = []

    # TODO: fixme upto
    if config["is_test"] == 1 or config["is_test"] == 2:
        test_videos = test_videos[:1]

    for test in tqdm(test_videos):
        print(test)
        path = test
        filename = path.split("labels/")[-1].split("_labels")[0].split("/")[-1]
        print(filename)
        # print(already_processed)
        if continuation and filename in already_processed:
            print("skipping since already processed")
            continue

        start = time()

        all_videos = labels[:]
        all_videos.remove(path)

        results_sink = _results_sink + filename + "/"
        check_directory(results_sink)

        x_test = np.load(pathForFile(videos, filename))[:crop]

        # back to grayscal
        if config["reduce_image"] == 1:
            # TODO: adjust here hyperparams
            x_test_new = []
            for idx, img in enumerate(x_test):
                # greyscale image
                img = rgb2gray(img)
                # crop image
                # img = img[32:-32,32:-32]
                # rescale image
                # img = imresize(img, 0.5)
                x_test_new.append(img)
            x_test = np.asarray(x_test_new)

        if config["reduce_image"] == 2:
            x_test_new = []
            for idx, img in enumerate(x_test):
                # greyscale image
                # TODO: normalize here by 32000????
                img = img_as_uint(rgb2gray(img))
                # crop image
                img = img[32:-32, 32:-32]
                # TODO: test here difference to float64
                # img = img_as_float32(img)
                x_test_new.append(img)
            x_test = np.asarray(x_test_new)

        y_test = np.load(path)[: x_test.shape[0]]
        dlc_test = np.load(pathForFile(dlc_annot, filename))[:crop]

        train_labels = all_videos.copy()
        x_train = []
        dlc_train = []
        y_train = []

        if config["is_test"] == 2:
            train_labels = train_labels[:5]

        for label in tqdm(train_labels):
            fname = label.split("labels/")[-1].split("_labels")[0].split("/")[-1]
            # TODO: same fix for DLC training
            _x_train = np.load(pathForFile(videos, fname))[:crop]

            if config["reduce_image"] == 1:
                x_train_new = []
                for idx, img in enumerate(_x_train):
                    # greyscale image
                    img = rgb2gray(img)
                    x_train_new.append(img)
                _x_train = np.asarray(x_train_new)

            if config["reduce_image"] == 2:
                x_train_new = []
                for idx, img in enumerate(_x_train):
                    # greyscale image
                    # TODO: normalize here by 32000????
                    img = img_as_uint(rgb2gray(img))
                    # crop image
                    img = img[32:-32, 32:-32]
                    # TODO: test here difference to float64
                    # img = img_as_float32(img)
                    x_train_new.append(img)
                _x_train = np.asarray(x_train_new)

            x_train.append(_x_train)

            # FIXME: different file length
            y_train.append(np.load(label)[: x_train[-1].shape[0]][:crop])
            last = np.load(pathForFile(dlc_annot, fname))[:crop]
            dlc_train.append(np.load(pathForFile(dlc_annot, fname))[:crop])
            print(np.unique(np.load(label)[: x_train[-1].shape[0]][:crop]))

        dlc_train = np.vstack(dlc_train)
        y_train = np.hstack(y_train)
        x_train = np.vstack(x_train)

        print("preparing data")

        dataloader = Dataloader(
            x_train,
            y_train,
            x_test,
            y_test,
            config["look_back"],
            with_dlc=config["train_dlc"],
            dlc_train=dlc_train,
            dlc_test=dlc_test,
        )

        # FIXME: remove?
        dataloader.change_dtype()

        dataloader.remove_behavior(behavior="jumping")

        # wether to use class weights later for training or not, calculate here?
        # FIXME: calculate these here or later?
        class_weights = None
        if config["use_class_weights"]:
            from sklearn.utils import class_weight

            class_weights = class_weight.compute_class_weight(
                "balanced", np.unique(y_train), y_train
            )

        print("normalizing")
        # FIXME: do normalize??
        if config["normalize"]:
            dataloader.normalize_data()

        if config["reduced_behavior"]:
            print("reducing labels")
            dataloader.reduce_labels(
                config["reduced_behavior_type"], config["reduced_behavior_num_labels"]
            )

        # preproc labels
        print("encoding")
        dataloader.encode_labels()

        if config["undersample"]:
            print("undersampling")
            dataloader.undersample_data()

        dataloader.categorize_data(num_classes)

        print("recurrent")
        if config["train_dlc"]:
            dataloader.create_recurrent_data_dlc()
        if config["train_ours"]:
            dataloader.create_recurrent_data()

        dataloader.create_flattened_data()

        if fraction is not None:
            dataloader.decimate_labels(percentage=fraction)

        print("data prepared!")

        # double check
        if config["reduce_image"] == 2 or len(dataloader.x_train.shape) < 4:
            dataloader.expand_dims()

        print("expanding dims")

        dataloader.change_dtype()

        print("data prepared")

        # intialize metrics
        my_metrics = Metrics()

        if config["train_dlc"]:
            optim = get_optimizer(config["dlc_model_optimizer"], config["dlc_model_lr"])
            # ### eval dlc model
            my_dlc_model = dlc_model_sturman(
                dataloader.dlc_train_flat.shape, num_classes
            )

            ### eval recurrent dlc model
            my_dlc_model_recurrent = dlc_model_sturman(
                dataloader.dlc_train_recurrent_flat.shape, num_classes
            )
            my_metrics.setModel(my_dlc_model_recurrent)

            # optim = get_optimizer(config['dlc_model_recurrent_optimizer'],
            #                       config['dlc_model_recurrent_lr'])

            optim = get_optimizer("rmsprop")

            my_dlc_model_recurrent, my_dlc_model_recurrent_history = train_model(
                my_dlc_model_recurrent,
                optim,
                config["dlc_model_recurrent_epochs"],
                config["dlc_model_recurrent_batch_size"],
                (dataloader.dlc_train_recurrent_flat, dataloader.y_train_recurrent),
                data_val=(
                    dataloader.dlc_test_recurrent_flat,
                    dataloader.y_test_recurrent,
                ),
                callbacks=[my_metrics],
                num_gpus=config["num_gpus"],
                loss=config["dlc_model_recurrent_loss"],
                class_weights=class_weights,
            )

            results_dict, results_array = eval_model(
                my_dlc_model_recurrent,
                dataloader.dlc_test_recurrent_flat,
                results_dict,
                results_array,
                filename,
                dataloader,
                "dlc_recurrent",
            )

        ### start with end-to-end model
        if config["train_ours"]:

            # TODO: make part of dataloader
            img_rows, img_cols = (
                dataloader.x_train.shape[1],
                dataloader.x_train.shape[2],
            )
            input_shape = (img_rows, img_cols, dataloader.x_train.shape[3])

            if config["backbone"] == "custom":
                recognition_model = classification_small(input_shape, num_classes)
            # recognition_model.summary()

            # if config['backbone'] == 'resnet':
            else:
                recognition_model = pretrained_recognition(
                    config["backbone"], input_shape, num_classes, fix_layers=False
                )

            # augmentation
            # TODO: check if augmentators make sense or too much
            augmentation = None
            if config["recognition_model_augmentation"]:
                sometimes = lambda aug: iaa.Sometimes(0.25, aug)
                seq = iaa.Sequential(
                    [
                        iaa.GaussianBlur((0, 2.0), name="GaussianBlur"),
                        #     iaa.Dropout(0.25, name="Dropout"),
                        #     iaa.AdditiveGaussianNoise(scale=0.01*255, name="MyLittleNoise"),
                        #     iaa.AdditiveGaussianNoise(loc=32, scale=0.0001*255, name="SomeOtherNoise"),
                        iaa.GammaContrast((0.5, 2.0)),
                        iaa.Fliplr(0.25),
                        iaa.ContrastNormalization((0.5, 1.5))
                        #     iaa.ContrastNormalization((0.5, 2.0), per_channel=0.5), # improve or worsen the contrast
                    ],
                    random_order=True,
                )
                augmentation = seq

            # initiate training callbacks
            # TODO: check parameters for these networks

            # TODO: make metrics and callbacks part of utils or so

            optim = get_optimizer(
                optim_name=config["recognition_model_optimizer"],
                lr=config["recognition_model_lr"],
            )

            if config["is_test"] == 2:
                config["recognition_model_epochs"] = 2

            # TODO: externalize
            def scheduler(epoch):
                new_lr = config["recognition_model_lr"] / np.power(1.2, epoch)
                print("reducing to new learning rate" + str(new_lr))
                return new_lr

            lr_callback = tf.keras.callbacks.LearningRateScheduler(scheduler)

            CB_es, CB_lr = get_callbacks()
            my_metrics = Metrics()
            my_metrics.setModel(recognition_model)

            CB_train = [CB_lr, CB_es, my_metrics]

            if config["lrschedule_rec"]:
                CB_train.append(lr_callback)

            recognition_model, recognition_model_history = train_model(
                recognition_model,
                optim,
                config["recognition_model_epochs"],
                config["recognition_model_batch_size"],
                (dataloader.x_train, dataloader.y_train),
                data_val=(dataloader.x_test, dataloader.y_test),
                callbacks=CB_train,
                loss=config["recognition_model_loss"],
                # TODO: activate augmentation
                augmentation=augmentation,
                num_gpus=config["num_gpus"],
            )
            # make a copy of the model for saving later
            # recognition_model_cp = keras.models.clone_model(recognition_model)
            # recognition_model_cp.build()
            # recognition_model_cp.set_weights(recognition_model.get_weights())

            results_dict, results_array = eval_model(
                recognition_model,
                dataloader.x_test,
                results_dict,
                results_array,
                filename,
                dataloader,
                "recognition_model",
            )

            # TODO: check here for different models
            # TODO: modulefy me
            # recognition_model.pop()

            if config["backbone"] == "custom":
                recognition_model.pop()
                recognition_model.pop()
                recognition_model.pop()

            if config["backbone"] == "xception":
                recognition_model.layers.pop()
                recognition_model.layers.pop()

            if config["fix_recognition"]:
                for layer in recognition_model.layers:
                    layer.trainable = False

            print(recognition_model.summary())

            recurrent_input_shape = (
                dataloader.x_train_recurrent.shape[1],
                dataloader.x_train_recurrent.shape[2],
                dataloader.x_train_recurrent.shape[3],
                dataloader.x_train_recurrent.shape[4],
            )

            sequential_model = recurrent_model_tcn(
                recognition_model, recurrent_input_shape, classes=num_classes,
            )

            my_metrics.setModel(sequential_model)

            optim = get_optimizer(
                config["sequential_model_optimizer"], config["sequential_model_lr"]
            )

            if config["is_test"] == 2:
                config["sequential_model_epochs"] = 1

            # TODO: recode here
            def scheduler(epoch):
                new_lr = config["sequential_model_lr"] / np.power(1.2, epoch)
                print("reducing to new learning rate" + str(new_lr))
                return new_lr

            lr_callback = tf.keras.callbacks.LearningRateScheduler(scheduler)
            if config["lrschedule_seq"]:
                CB_train = [CB_lr, CB_es, my_metrics, lr_callback]
            else:
                CB_train = [CB_lr, CB_es, my_metrics]

            sequential_model, sequential_model_history = train_model(
                sequential_model,
                optim,
                config["sequential_model_epochs"],
                config["sequential_model_batch_size"],
                (dataloader.x_train_recurrent, dataloader.y_train_recurrent),
                data_val=(dataloader.x_test_recurrent, dataloader.y_test_recurrent),
                callbacks=CB_train,
                loss=config["sequential_model_loss"],
                num_gpus=config["num_gpus"],
                # TODO: activate augmentation for recurrent trainign as well?
            )

            results_dict, results_array = eval_model(
                sequential_model,
                dataloader.x_test_recurrent,
                results_dict,
                results_array,
                filename,
                dataloader,
                "sequential_model",
            )

            # append ground truth to results
            # TODO: have only recurrent gt
            results_dict["gt" + filename] = y_test[
                dataloader.look_back : -dataloader.look_back
            ]

            for el in y_test[dataloader.look_back : -dataloader.look_back]:
                # FIXME: do better
                try:
                    results_array.append(
                        np.hstack(
                            [
                                "gt",
                                filename,
                                1,
                                1,
                                1,
                                1,
                                dataloader.encode_label([el])[0],
                                el,
                            ]
                        )
                    )
                except ValueError:
                    results_array.append(
                        np.hstack(["gt", filename, 1, 1, 1, 1, "none", el])
                    )

            recognition_model.save_weights(
                results_sink + filename + "_SIPEC_recognitionNet" + ".h5"
            )
            sequential_model.save_weights(
                results_sink + filename + "_SIPEC_behaviorNet" + ".h5"
            )

            save_dict(
                results_sink + filename + "_SIPEC_recognitionNet_history" + ".pkl",
                recognition_model_history.history,
            )
            save_dict(
                results_sink + filename + "_SIPEC_behaviorNet_history" + ".pkl",
                sequential_model_history.history,
            )

            np.save(_results_sink + "results_array" + ".npy", results_array)
            save_dict(_results_sink + "results_dict" + ".npy", results_dict)

            print("epoch done")

        print("took overall")
        print(str(time() - start))

    return results_array, results_dict


def main():
    args = parser.parse_args()
    config_name = args.config_name
    gpu_name = args.gpu
    continuation = args.continuation
    random_seed = args.random_seed
    fraction = args.fraction

    fraction_string = ""
    if fraction is not None:
        fraction_string = str(fraction)

    # init stuff

    base_path = "/media/nexus/storage5/swissknife_data/mouse"
    mouse_data = MouseDataset(base_path)
    config = load_config("../configs/behavior/shared_config")
    exp_config = load_config("./configs/behavior/reproduce_configs/" + config_name)

    config.update(exp_config)

    ### setting up sessions
    # set gpu
    keras_config = tf.ConfigProto()
    keras_config.gpu_options.allow_growth = True
    keras_config.gpu_options.visible_device_list = str(gpu_name)

    # set all the randomness according to
    # https://stackoverflow.com/questions/50659482/why-cant-i-get-reproducible-results-in-keras-even-though-i-set-the-random-seeds
    rnd = config["random_seed"]
    if random_seed is not None:
        rnd = random_seed
    set_random_seed(rnd)

    # double check this
    # TODO:
    # session_conf = tf.ConfigProto(intra_op_parallelism_threads=1, inter_op_parallelism_threads=1)
    sess = tf.Session(graph=tf.get_default_graph(), config=keras_config)
    K.set_session(sess)

    num_classes = 4
    if config["reduced_behavior"]:
        num_classes = 2

    if config["train_dlc"]:
        results_sink = (
            "/media/nexus/storage4/swissknife_results/behavior/dlc_"
            + config["experiment_name"]
            + "_"
            + str(rnd)
            + "_"
            + fraction_string
            + "/"
        )
    else:
        results_sink = (
            "/media/nexus/storage4/swissknife_results/behavior/ours_"
            + config["experiment_name"]
            + "_"
            + str(rnd)
            + "_"
            + fraction_string
            + "/"
        )

    # FIXME: check for existence already before
    if not continuation:
        check_directory(results_sink)

    # save config
    with open(results_sink + "config.json", "w") as f:
        json.dump(config, f)
    f.close()

    print(config)

    results_array, results_dict = run_experiment(
        base_path,
        config,
        num_classes=num_classes,
        results_sink=results_sink,
        continuation=continuation,
        fraction=fraction,
    )

    # save results
    results_array = np.asarray(results_array)
    results = pd.DataFrame(
        {
            "Method": results_array[:, 0],
            "Video": results_array[:, 1],
            "Conf_1": results_array[:, 2],
            "Conf_2": results_array[:, 3],
            "Conf_3": results_array[:, 4],
            "Conf_4": results_array[:, 5],
            "Behaviour_numerical": results_array[:, 6],
            "Behaviour": results_array[:, 7],
        }
    )
    results.to_csv(results_sink + "behavior_results_multi.csv")
    with open(results_sink + "behavior_results_single.pkl", "wb") as f:
        pickle.dump(results_dict, f)
    f.close()
    #
    # for el in my_models.keys():
    #     # my_models[el].save(results_sink + el + '.h5')
    #     my_models[el].save_weights(results_sink + el + '.h5')


parser = ArgumentParser()

parser.add_argument(
    "--config_name",
    action="store",
    dest="config_name",
    type=str,
    default="behavior_config_baseline",
    help="behavioral config to use",
)

parser.add_argument(
    "--gpu",
    action="store",
    dest="gpu",
    type=int,
    default=0,
    help="filename of the video to be processed (has to be a segmented one)",
)
parser.add_argument(
    "--continuation",
    action="store",
    dest="continuation",
    type=int,
    default=0,
    help="continuation of started training",
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

if __name__ == "__main__":
    main()
