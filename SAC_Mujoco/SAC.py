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

device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')

if T.backends.cudnn.enabled:
    T.backends.cudnn.benchmark = False
    T.backends.cudnn.deterministic = True

seed = 100
T.manual_seed(seed)
T.cuda.manual_seed(seed)
np.random.seed(seed)
random.seed(seed)
print('Using GPU : ', T.cuda.is_available() , ' |  Seed : ', seed)

def _layer_norm(layer, std=1.0, bias_const=1e-6):
    if type(layer) == nn.Linear:
        T.nn.init.orthogonal_(layer.weight, std)
        T.nn.init.constant_(layer.bias, bias_const)

class ActionNormalizer(gym.ActionWrapper):
    '''This code from OpenAI Gym '''
    def action(self, action: np.ndarray) -> np.ndarray:
        low = self.action_space.low
        high = self.action_space.high
        scale_factor = (high - low) / 2
        reloc_factor = high - scale_factor
        action = action * scale_factor + reloc_factor
        action = np.clip(action, low, high)
        return action

    def reverse_action(self, action: np.ndarray) -> np.ndarray:
        low = self.action_space.low
        high = self.action_space.high
        scale_factor = (high - low) / 2
        reloc_factor = high - scale_factor
        action = (action - reloc_factor) / scale_factor
        action = np.clip(action, -1.0, 1.0)
        return action


class SACAgent:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

        dirPath='/home/nam/Reinforcement_learning/SAC_Mujoco'
        self.checkpoint = os.path.join(dirPath,'alpha_optimizer')

        self.env = gym.make('Walker2d-v2')
        self.env = RescaleAction(self.env, -1, 1)
        # self.env = ActionNormalizer(self.env)

        self.n_states = self.env.observation_space.shape[0]
        self.n_actions = self.env.action_space.shape[0]
        # self.max_action = float(self.env.action_space.high[0])
        self.max_action = 1

        self.memory = ReplayBuffer(self.memory_size, self.n_states, self.n_actions, self.batch_size)

        self.target_entropy = -self.n_actions
        self.log_alpha = T.zeros(1, requires_grad=True, device=device)
        self.alpha = self.log_alpha.exp()
        self.alpha_optimizer = optim.Adam([self.log_alpha], lr=self.learning_rate)

        self.actor = ActorNetwork(self.n_states, self.n_actions, self.max_action, self.learning_rate)
        self.actor.apply(_layer_norm)

        self.critic_eval = CriticNetwork(self.n_states, self.n_actions, self.learning_rate)
        self.critic_eval.apply(_layer_norm)
        self.critic_target = copy.deepcopy(self.critic_eval)
        self.critic_target.eval()
        for p in self.critic_target.parameters():
            p.requires_grad = False

        self.transition = list()


    def choose_action(self, state):
        # if (self.total_episode < self.train_start) and not self.test_mode:
        #     action = self.env.action_space.sample()
        # elif self.test_mode is True:
        #     action = self.actor(T.FloatTensor(state).to(self.actor.device), test_mode=True, with_logprob=False)[0].detach().cpu().numpy()
        # elif (self.total_episode > self.train_start) and not self.test_mode:
        #     action, _ = self.actor(T.FloatTensor(state).to(self.actor.device))[0].detach().cpu().numpy()


        if self.time_step < self.random_action:
            action = self.env.action_space.sample()
        else:
            action, _ = self.actor(T.FloatTensor(state).to(self.actor.device))
            action = action.detach().cpu().numpy()
        self.transition = [state, action]
        return action

    def target_soft_update(self):
        tau = self.tau
        with T.no_grad():
            for t_p, l_p in zip(self.critic_target.parameters(), self.critic_eval.parameters()):
                t_p.data.copy_(tau * l_p.data + (1 - tau) * t_p.data)

    def learn(self):
        samples = self.memory.sample_batch()
        state = T.FloatTensor(samples["state"]).to(self.actor.device)
        next_state = T.FloatTensor(samples["next_state"]).to(self.actor.device)
        action = T.FloatTensor(samples["action"].reshape(-1, self.n_actions)).to(self.actor.device)
        reward = T.FloatTensor(samples["reward"].reshape(-1, 1)).to(self.actor.device)
        done = T.FloatTensor(samples["done"].reshape(-1, 1)).to(self.actor.device)
        mask = (1 - done).to(self.actor.device)

        # critic update
        with T.no_grad():
            next_action, next_log_prob = self.actor(next_state)
            q1_target, q2_target = self.critic_target(next_state, next_action)
            q_target = T.min(q1_target, q2_target)
            value_target = reward + self.GAMMA * (q_target - self.alpha * next_log_prob)
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

        if self.time_step % self.update_time == 0 :
            self.target_soft_update()

    def save_models(self):
        print('------ save models ------')
        self.actor.save_models()
        self.critic_eval.save_models()

        T.save(self.alpha_optimizer.state_dict(), self.checkpoint)

    def load_models(self):
        print('------ load models ------')
        self.alpha_optimizer.load_state_dict(T.load(self.checkpoint))

        self.actor.load_models()

        self.critic_eval.load_models()
        self.critic_target = copy.deepcopy(self.critic_eval)
