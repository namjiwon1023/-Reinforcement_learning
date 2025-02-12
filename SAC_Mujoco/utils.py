import numpy as np
import matplotlib.pyplot as plt
import torch as T
import torch.nn as nn
import random

def _layer_norm(layer, std=1.0, bias_const=1e-6):
    if type(layer) == nn.Linear:
        nn.init.orthogonal_(layer.weight, std)
        nn.init.constant_(layer.bias, bias_const)


def random_seed(seed):
    if T.backends.cudnn.enabled:
        T.backends.cudnn.benchmark = False
        T.backends.cudnn.deterministic = True

    T.manual_seed(seed)
    T.cuda.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    print('Using GPU : ', T.cuda.is_available() , ' |  Seed : ', seed)

def _plot(scores):
    z = [c+1 for c in range(len(scores))]
    running_avg = np.zeros(len(scores))
    for e in range(len(running_avg)):
        running_avg[e] = np.mean(scores[max(0, e-10):(e+1)])
    plt.cla()
    plt.title("Total_scores")
    plt.grid(True)
    plt.xlabel("Episode_Reward")
    plt.ylabel("Total reward")
    plt.plot(scores, "r-", linewidth=1.5, label="sac_episode_reward")
    plt.plot(z, running_avg, "b-", linewidth=1.5, label="sac_avg_reward")
    plt.legend(loc="best", shadow=True)
    plt.pause(0.1)
    plt.savefig('./sac.jpg')
    plt.show()
