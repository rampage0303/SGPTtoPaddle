from collections import OrderedDict

import numpy as np
import paddle
import torch
from paddlenlp.transformers import BertForPretraining as PDBertForMaskedLM
from transformers import BertForMaskedLM as PTBertForMaskedLM


def convert_pytorch_checkpoint_to_paddle(
        pytorch_checkpoint_path="./BERT_source/pytorch_model.bin",
        paddle_dump_path="./BERT_source/model_state.pdparams",
        version="old", ):
    hf_to_paddle = {
        "embeddings.LayerNorm": "embeddings.layer_norm",
        "encoder.layer": "encoder.layers",
        "attention.self.query": "self_attn.q_proj",
        "attention.self.key": "self_attn.k_proj",
        "attention.self.value": "self_attn.v_proj",
        "attention.output.dense": "self_attn.out_proj",
        "intermediate.dense": "linear1",
        "output.dense": "linear2",
        "attention.output.LayerNorm": "norm1",
        "output.LayerNorm": "norm2",
        "predictions.decoder": "predictions.decoder",
        "predictions.transform.dense": "predictions.transform",
        "predictions.transform.LayerNorm": "predictions.layer_norm",
    }
    do_not_transpose = []
    if version == "old":
        hf_to_paddle.update({
            "predictions.bias": "predictions.decoder.bias",
            ".gamma": ".weight",
            ".beta": ".bias",
        })
        # do_not_transpose = do_not_transpose + ["predictions.decoder.weight"]

    pytorch_state_dict = torch.load(
        pytorch_checkpoint_path, map_location="cpu")
    paddle_state_dict = OrderedDict()
    for k, v in pytorch_state_dict.items():
        is_transpose = False
        if k[-7:] == ".weight":
            # embeddings.weight and LayerNorm.weight do not transpose
            if all(d not in k for d in do_not_transpose):
                if ".embeddings." not in k and ".LayerNorm." not in k:
                    if v.ndim == 2:
                        v = v.transpose(0, 1)
                        is_transpose = True
        if k == "cls.predictions.decoder.weight":
            v = v.transpose(0, 1)
        oldk = k
        for hf_name, pd_name in hf_to_paddle.items():
            k = k.replace(hf_name, pd_name)

        # add prefix `bert.`
        if "bert." not in k and "cls." not in k and "classifier" not in k:
            k = "bert." + k

        if k == "cls.predictions.decoder.bias":
            k = k.replace("cls.predictions.decoder.bias", "cls.predictions.decoder_bias")
        print(f"Converting: {oldk} => {k} | is_transpose {is_transpose}")
        paddle_state_dict[k] = v.data.numpy()

    paddle.save(paddle_state_dict, paddle_dump_path)


def compare(out_torch, out_paddle):
    out_torch = out_torch.detach().numpy()
    out_paddle = out_paddle.detach().numpy()
    assert out_torch.shape == out_paddle.shape
    abs_dif = np.abs(out_torch - out_paddle)
    mean_dif = np.mean(abs_dif)
    max_dif = np.max(abs_dif)
    min_dif = np.min(abs_dif)
    print("mean_dif:{}".format(mean_dif))
    print("max_dif:{}".format(max_dif))
    print("min_dif:{}".format(min_dif))


def test_forward():
    paddle.set_device("cpu")
    model_torch = PTBertForMaskedLM.from_pretrained("./BERT_source")
    model_paddle = PDBertForMaskedLM.from_pretrained("./BERT_source")
    model_torch.eval()
    model_paddle.eval()
    np.random.seed(42)
    x = np.random.randint(
        1, model_paddle.bert.config["vocab_size"], size=(4, 64))
    input_torch = torch.tensor(x, dtype=torch.int64)
    out_torch = model_torch(input_torch)[0]

    input_paddle = paddle.to_tensor(x, dtype=paddle.int64)
    out_paddle = model_paddle(input_paddle)[0]

    print("torch result shape:{}".format(out_torch.shape))
    print("paddle result shape:{}".format(out_paddle.shape))
    compare(out_torch, out_paddle)


if __name__ == "__main__":
    convert_pytorch_checkpoint_to_paddle(
        "./BERT_source/pytorch_model.bin",
        "./BERT_source/model_state.pdparams")
    test_forward()
    # torch result shape:torch.Size([4, 64, 30522])
    # paddle result shape:[4, 64, 30522]
    # mean_dif:1.666686512180604e-05
    # max_dif:0.00015211105346679688
    # min_dif:0.0

# [2023-10-30 20:06:59,743] [ WARNING] - Some weights of the model checkpoint at ./BERT_source were not used when initializing BertForPretraining: ['cls.predictions.decoder_weight']
# - This IS expected if you are initializing BertForPretraining from the checkpoint of a model trained on another task or with another architecture (e.g. initializing a BertForSequenceClassification model from a BertForPreTraining model).
# - This IS NOT expected if you are initializing BertForPretraining from the checkpoint of a model that you expect to be exactly identical (initializing a BertForSequenceClassification model from a BertForSequenceClassification model).
# [2023-10-30 20:06:59,744] [ WARNING] - Some weights of BertForPretraining were not initialized from the model checkpoint at ./BERT_source and are newly initialized: ['cls.predictions.decoder.weight', 'cls.predictions.decoder.bias']
# You should probably TRAIN this model on a down-stream task to be able to use it for predictions and inference.
# torch result shape:torch.Size([4, 64, 30522])
# paddle result shape:[4, 64, 30522]
# mean_dif:4.299612555769272e-06
# max_dif:3.8623809814453125e-05
# min_dif:0.0
# Skip loading for cls.predictions.decoder.weight. cls.predictions.decoder.weight receives a shape [768, 30522], but the expected shape is [30522, 768].?