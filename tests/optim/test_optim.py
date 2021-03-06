from __future__ import absolute_import, division, print_function

from unittest import TestCase

import pytest
import torch

import pyro
import pyro.optim as optim
from pyro.distributions import Normal
from pyro.infer import SVI


class OptimTests(TestCase):

    def setUp(self):
        # normal-normal; known covariance
        self.lam0 = torch.tensor([0.1])  # precision of prior
        self.loc0 = torch.tensor([0.5])  # prior mean
        # known precision of observation noise
        self.lam = torch.tensor([6.0])
        self.data = torch.tensor([1.0])  # a single observation

    def test_per_param_optim(self):
        self.do_test_per_param_optim("loc_q", "log_sig_q")
        self.do_test_per_param_optim("log_sig_q", "loc_q")

    # make sure lr=0 gets propagated correctly to parameters of our choice
    def do_test_per_param_optim(self, fixed_param, free_param):
        pyro.clear_param_store()

        def model():
            prior_dist = Normal(self.loc0, torch.pow(self.lam0, -0.5))
            loc_latent = pyro.sample("loc_latent", prior_dist)
            x_dist = Normal(loc_latent, torch.pow(self.lam, -0.5))
            pyro.sample("obs", x_dist, obs=self.data)
            return loc_latent

        def guide():
            loc_q = pyro.param(
                "loc_q",
                torch.zeros(1, requires_grad=True))
            log_sig_q = pyro.param(
                "log_sig_q",
                torch.zeros(1, requires_grad=True))
            sig_q = torch.exp(log_sig_q)
            pyro.sample("loc_latent", Normal(loc_q, sig_q))

        def optim_params(module_name, param_name):
            if param_name == fixed_param:
                return {'lr': 0.00}
            elif param_name == free_param:
                return {'lr': 0.01}

        adam = optim.Adam(optim_params)
        adam2 = optim.Adam(optim_params)
        svi = SVI(model, guide, adam, loss="ELBO", trace_graph=True)
        svi2 = SVI(model, guide, adam2, loss="ELBO", trace_graph=True)

        svi.step()
        adam_initial_step_count = list(adam.get_state()['loc_q']['state'].items())[0][1]['step']
        adam.save('adam.unittest.save')
        svi.step()
        adam_final_step_count = list(adam.get_state()['loc_q']['state'].items())[0][1]['step']
        adam2.load('adam.unittest.save')
        svi2.step()
        adam2_step_count_after_load_and_step = list(adam2.get_state()['loc_q']['state'].items())[0][1]['step']

        assert adam_initial_step_count == 1
        assert adam_final_step_count == 2
        assert adam2_step_count_after_load_and_step == 2

        free_param_unchanged = torch.equal(pyro.param(free_param).data, torch.zeros(1))
        fixed_param_unchanged = torch.equal(pyro.param(fixed_param).data, torch.zeros(1))
        assert fixed_param_unchanged and not free_param_unchanged


@pytest.mark.parametrize('factory', [optim.Adam, optim.ClippedAdam, optim.RMSprop, optim.SGD])
def test_autowrap(factory):
    instance = factory({})
    assert instance.pt_optim_constructor.__name__ == factory.__name__
