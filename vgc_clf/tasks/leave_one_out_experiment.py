import argparse
import json
import numpy as np
import pandas as pd
import warnings

from sklearn.metrics import roc_auc_score

from vgc_clf.sampler.sampler import Sampler
from vgc_clf.ensemble.ensemble import Ensemble
from vgc_clf.utils import data_frame_utils as df_utils
from vgc_clf.utils import ensemble_utils as ens_utils

warnings.filterwarnings(action="ignore")


def run_leave_one_out_experiment(df, loo_variable, subject_dictionary, sampler_dictionary, ensemble_dictionary,
                                 verbose=False):
    subject_column = subject_dictionary["subject_id_column"]
    subject_info = subject_dictionary["subject_data_columns"]
    subject_target = subject_dictionary["target_variable"]

    df_dgn = df_utils.get_subjects_data_frame(df=df, subject_column_name=subject_column,
                                              subject_info_columns=subject_info)

    loo_dfs = df_utils.generate_leave_one_out_batch(signal_df=df, subjects_df=df_dgn,
                                                    subject_id_column=subject_column,
                                                    strata_column=loo_variable)

    fraction = sampler_dictionary["train_test_fraction"]
    valid_variables = sampler_dictionary["input_variables"]
    target_variable = sampler_dictionary["target_variable"]
    n_train_batches = sampler_dictionary["n_train_batches"]
    train_batches_size = sampler_dictionary["train_batches_size"]
    n_test_batches = sampler_dictionary["n_test_batches"]
    test_batches_size = sampler_dictionary["test_batches_size"]

    classifier_list = [clf for clf in ens_utils.get_classifier_objects(ensemble_dictionary["classifier_list"])]
    node_sizes = ensemble_dictionary["node_sizes"]
    kwargs_list = ensemble_dictionary["kwargs_list"]
    score_cap = ensemble_dictionary["score_cap"]
    get_best = ensemble_dictionary["get_best"]
    class_threshold = ensemble_dictionary["class_threshold"]

    scores = []
    cv_batches = len(df[loo_variable].unique())
    for k, (df_fit, df_val, train_index, _) in enumerate(loo_dfs):
        print(f"------ITERATION {k + 1} of {cv_batches}", flush=True)

        ts = int(np.ceil((1. - fraction) * len(train_index)))
        df_train, df_test, _, _ = df_utils.get_train_validation_from_data_frame(signal_df=df_fit,
                                                                                subjects_df=df_dgn.loc[train_index, :],
                                                                                subject_id_column=subject_column,
                                                                                target_variable=subject_target,
                                                                                test_size=ts)

        train_samplings = Sampler()
        test_samplings = Sampler()

        train_samplings.generate_batches(df_train,
                                         n_batches=n_train_batches,
                                         batch_len=train_batches_size,
                                         target_variable=target_variable,
                                         input_variables=valid_variables,
                                         verbose=verbose)

        test_samplings.generate_batches(df_test,
                                        n_batches=n_test_batches,
                                        batch_len=test_batches_size,
                                        target_variable=target_variable,
                                        input_variables=valid_variables,
                                        verbose=verbose)

        vgc_classifier = Ensemble(classifier_list=classifier_list, node_sizes=node_sizes, kwargs_list=kwargs_list)
        vgc_classifier.fit(batch_list_train=train_samplings, batch_list_test=test_samplings,
                           score_cap=score_cap, get_best=get_best, verbose=verbose)

        prd_prb = vgc_classifier.predict_proba(df=df_val, verbose=verbose)
        prd = (prd_prb > class_threshold) * 1
        it_performance = [(prd == df_val[target_variable]).mean(),
                          1 - (prd[df_val[target_variable] == 0] == [0] * len(
                              df_val[df_val[target_variable] == 0])).mean(),
                          1 - (prd[df_val[target_variable] == 1] == [1] * len(
                              df_val[df_val[target_variable] == 1])).mean()]
        scores.append(it_performance)

        print(f"---SCORE: {scores[-1][0]}", flush=True)

    print("------END OF LEAVE-ONE-OUT VALIDATION", flush=True)

    scores = pd.DataFrame(scores, columns=["accuracy", "FNR", "FPR", "roc_auc"])

    print(f"Average score: {np.round(scores.accuracy.mean(), 6)}")
    print(f"Average FNR: {np.round(scores.FNR.mean(), 6)}")
    print(f"Average FPR: {np.round(scores.FPR.mean(), 6)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", "--data_frame", help="Path to data frame containing signal data to build the experiment.",
                        type=str, required=True)
    parser.add_argument("-v", "--loo_variable", help="Variable with respect to which generate the leave-one-out batch",
                        type=str, required=True)
    parser.add_argument("-p", "--subject_json", help="Path to json file containing subject/patient data frame "
                                                     "generation info.", type=str, required=True)
    parser.add_argument("-s", "--sampler_json", help="Path to json file containing sampler generation info.", type=str,
                        required=True)
    parser.add_argument("-e", "--ensemble_json", help="Path to json file containing ensemble generation info.",
                        type=str, required=True)
    parser.add_argument("--verbose", help="Be verbose on progress on screen", default=False, action="store_true")

    args = parser.parse_args()

    df_in = pd.read_csv(args.data_frame, sep=",")
    subject_dict = json.load(open(args.subject_json, "r"))
    sampler_dict = json.load(open(args.sampler_json, "r"))
    ensemble_dict = json.load(open(args.ensemble_json, "r"))

    run_leave_one_out_experiment(df=df_in,
                                 loo_variable=args.loo_variable,
                                 subject_dictionary=subject_dict,
                                 sampler_dictionary=sampler_dict,
                                 ensemble_dictionary=ensemble_dict,
                                 verbose=args.verbose)