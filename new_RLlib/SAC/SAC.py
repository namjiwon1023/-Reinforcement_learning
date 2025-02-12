import os
import torch as T
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import numpy as np
import copy
import gym
from gym.wrappers import RescaleAction
import random

from ReplayBuffer import ReplayBuffer
from ActorNetwork import ActorNetwork
from CriticNetwork import CriticNetwork
from utils import _layer_norm

class SACAgent:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')
        self.dirPath='/home/nam/Reinforcement_learning/new_RLlib/SAC/checkpoint'
        self.alpha_checkpoint = os.path.join(self.dirPath, 'alpha_optimizer')

        self.env = gym.make('Walker2d-v2')
        self.env = RescaleAction(self.env, -1, 1)

        self.n_states = self.env.observation_space.shape[0]
        self.n_actions = self.env.action_space.shape[0]
        self.n_hiddens = 256

        self.memory = ReplayBuffer(self.memory_size, self.n_states, self.n_actions, self.use_cuda)

        self.target_entropy = -self.n_actions
        self.log_alpha = T.zeros(1, requires_grad=True, device=self.device)
        self.alpha = self.log_alpha.exp()
        self.alpha_optimizer = optim.Adam([self.log_alpha], lr=self.learning_rate)

        self.actor = ActorNetwork(self.n_states, self.n_actions, self.n_hiddens, self.learning_rate, self.dirPath)
        self.actor.apply(_layer_norm)

        self.critic_eval = CriticNetwork(self.n_states, self.n_actions, self.n_hiddens, self.learning_rate, self.dirPath)
        self.critic_eval.apply(_layer_norm)
        self.critic_target = copy.deepcopy(self.critic_eval)
        self.critic_target.eval()
        for p in self.critic_target.parameters():
            p.requires_grad = False

        self.transition = list()


    def choose_action(self, state, test_mode=False):
        if test_mode is True:
            action, _ = self.actor(T.as_tensor(state, dtype=T.float32, device=self.actor.device), test_mode=True, with_logprob=False)
            action = action.detach().cpu().numpy()
        else:
            if self.total_episode < self.train_start_episode:
                action = self.env.action_space.sample()
            else:
                action, _ = self.actor(T.as_tensor(state, dtype=T.float32, device=self.actor.device))
                action = action.detach().cpu().numpy()

        self.transition = [state, action]
        return action

    def target_soft_update(self):
        tau = self.tau
        with T.no_grad():
            for t_p, l_p in zip(self.critic_target.parameters(), self.critic_eval.parameters()):
                t_p.data.copy_(tau * l_p.data + (1 - tau) * t_p.data)

    def learn(self):
        # k = 1.0 + len(self.memory) / self.memory_size
        # batch_size_ = int(self.batch_size * k)

        # self.learn_iter += 1
        # samples = self.memory.sample_batch(batch_size_)
        samples = self.memory.sample_batch(self.batch_size)
        state = samples["state"]
        next_state = samples["next_state"]
        action = samples["action"].reshape(-1, self.n_actions)
        reward = samples["reward"].reshape(-1, 1)
        mask = samples["mask"].reshape(-1, 1)

        # critic update
        with T.no_grad():
            next_action, next_log_prob = self.actor(next_state)
            q1_target, q2_target = self.critic_target(next_state, next_action)
            q_target = T.min(q1_target, q2_target)
            value_target = reward + (q_target - self.alpha * next_log_prob) * mask
        q1_eval, q2_eval = self.critic_eval(state, action)
        critic_loss = F.mse_loss(q1_eval, value_target) + F.mse_loss(q2_eval, value_target)

        self.critic_eval.optimizer.zero_grad()
        critic_loss.backward()
        self.critic_eval.optimizer.step()

        for p in self.critic_eval.parameters():
            p.requires_grad = False

        new_action, new_log_prob = self.actor(state)
        q_1, q_2 = self.critic_eval(state, new_action)
        q = T.min(q_1, q_2)
        actor_loss = (self.alpha * new_log_prob - q).mean()
        alpha_loss = -self.log_alpha * (new_log_prob.detach() + self.target_entropy).mean()

        self.actor.optimizer.zero_grad()
        actor_loss.backward()
        self.actor.optimizer.step()

        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.alpha_optimizer.step()

        for p in self.critic_eval.parameters():
            p.requires_grad = True

        self.alpha = self.log_alpha.exp()

        if self.learn_iter % self.soft_update_time == 0 :
            self.target_soft_update()

    def save_models(self):
        print('------ save models ------')
        self.actor.save_models()
        self.critic_eval.save_models()

        T.save(self.alpha_optimizer.state_dict(), self.alpha_checkpoint)

    def load_models(self):
        print('------ load models ------')
        self.alpha_optimizer.load_state_dict(T.load(self.alpha_checkpoint))

        self.actor.load_models()

        self.critic_eval.load_models()
        self.critic_target = copy.deepcopy(self.critic_eval)

    # def evaluate_agent(self, n_starts=1):
    #     reward_sum = 0
    #     for _ in range(n_starts):
    #         done = False
    #         state = self.env.reset()
    #         while (not done):
    #             action = self.choose_action(state, test_mode=True)
    #             next_state, reward, done, _ = self.env.step(action)
    #             reward_sum += reward
    #             state = next_state
    #     return reward_sum / n_starts