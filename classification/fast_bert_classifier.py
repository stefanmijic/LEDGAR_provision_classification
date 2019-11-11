# https://github.com/kaushaltrivedi/fast-bert

import os
import logging
import torch
from sklearn.preprocessing import MultiLabelBinarizer
from fast_bert.data_cls import BertDataBunch
from fast_bert.learner_cls import BertLearner
from fast_bert.metrics import accuracy
from utils import split_corpus, SplitDataSet, evaluate_multilabels, \
    tune_clf_thresholds


def write_csv(x, y, label_set_list, outfile):
    with open(outfile, 'w') as f:
        f.write("text, " + ','.join(label_set_list) + '\n')
        for sample, labels in zip(x, y):
            f.write('"' + sample.replace('\t', ' ').replace('"', "'") + '"')
            f.write(',')
            f.write(','.join([str(i) for i in labels]))
            f.write('\n')


if __name__ == '__main__':
    corpus_file = 'data/sec_corpus_2016-2019_clean_NDA_PTs2.jsonl'
    classifier_file = 'saved_models/fastbert_nda.pkl'
    # corpus_file = 'data/sec_corpus_2016-2019_clean_proto.jsonl'
    # classifier_file = 'saved_models/fastbert_proto.pkl'

    logger = logging.getLogger()
    # device_cuda = torch.device('cuda' if torch.cuda.is_avaliable() else 'cpu')
    # device_cuda = 'cpu'
    device_cuda = torch.device("cuda")
    metrics = [{'name': 'accuracy', 'function': accuracy}]

    print('Loading corpus from', corpus_file)
    dataset: SplitDataSet = split_corpus(corpus_file)
    print(len(dataset.y_train), 'training samples')
    print(len(dataset.y_test), 'test samples')
    print(len(dataset.y_dev), 'dev samples')
    label_set = set(l for labels in dataset.y_train for l in labels)
    print('Label set size:', len(label_set))

    mlb = MultiLabelBinarizer().fit(dataset.y_train)
    train_y = mlb.transform(dataset.y_train)
    test_y = mlb.transform(dataset.y_train)
    dev_y = mlb.transform(dataset.y_dev)

    DATA_PATH = 'data/'
    LABEL_PATH = 'data/'
    OUTPUT_DIR = 'data/'

    # create the CSVs
    write_csv(dataset.x_train, train_y, list(mlb.classes_), os.path.join(DATA_PATH, 'train.csv'))
    write_csv(dataset.x_test, test_y, list(mlb.classes_), os.path.join(DATA_PATH, 'test.csv'))
    write_csv(dataset.x_dev, dev_y, list(mlb.classes_), os.path.join(DATA_PATH, 'dev.csv'))
    # write label file
    with open(os.path.join(LABEL_PATH, 'labels.csv'), 'w') as f:
        for label in label_set:
            f.write(label + '\n')

    databunch = BertDataBunch(DATA_PATH, LABEL_PATH,
                              tokenizer='bert-base-uncased',
                              train_file='train.csv',
                              val_file='test.csv',
                              label_file='labels.csv',
                              text_col='text',
                              label_col=list(mlb.classes_),
                              batch_size_per_gpu=16,
                              max_seq_length=512,
                              multi_gpu=False,
                              multi_label=True,
                              model_type='bert')

    learner = BertLearner.from_pretrained_model(
        databunch,
        pretrained_path='bert-base-uncased',
        metrics=metrics,
        device=device_cuda,
        logger=logger,
        output_dir=OUTPUT_DIR,
        finetuned_wgts_path=None,
        warmup_steps=500,
        multi_gpu=False,
        is_fp16=True,
        multi_label=True,
        logging_steps=50)

    learner.fit(epochs=1,
                lr=6e-5,
                validate=True,  # Evaluate the model after each epoch
                schedule_type = "warmup_cosine",
                optimizer_type = "lamb")

    learner.save_model()