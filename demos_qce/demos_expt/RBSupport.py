''' Some functions for RB support '''
import numpy as np
import pickle
import cirq

def gauss(mu=0, si=0, length=100, maxv=30000):
    x = np.arange(0, length)
    y = 1/np.sqrt(2*np.pi*si**2)*np.exp(-(x-mu)**2/2/si**2)
    y = y-y[0]
    y = y/np.max(y)*maxv
    return y

def generate_2qgateset(config):
    return {
              "I": {
                  "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                 length=4 * 16*config["pi_sigma"], maxv=32000),
                  "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                     length=4 * 16*config["pi_sigma"], maxv=32000),
                  "phase": 0, "gain": 0, "style": "arb",

              },
            "sqrtiSWAP": {
                "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                               length=4 * 16*config["pi_sigma"], maxv=5000),
                "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                   length=4 * 16*config["pi_sigma"], maxv=5000),
                "phase": 0, "gain": config['pi_gain'], "style": "arb",
            },
            "sqrtbSWAP": {
                "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                               length=4 * 16*config["pi_sigma"], maxv=10000),
                "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                   length=4 * 16*config["pi_sigma"], maxv=10000),
                "phase": 0, "gain": config['pi_gain'], "style": "arb",
            },
              "X": {
                  "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                 length=4 * 16*config["pi_sigma"], maxv=32000),
                  "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                     length=4 * 16*config["pi_sigma"], maxv=32000),
                  "phase": 0, "gain": config['pi_gain'], "style": "arb",
              },
            "Y": {
                "idata": 0 * gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                               length=4 * 16 * config["pi_sigma"], maxv=32000),
                "qdata": gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                                   length=4 * 16 * config["pi_sigma"], maxv=32000),
                "phase": 0, "gain": config['pi_gain'], "style": "arb",
            },
              "Z": {
                  "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                 length=4 * 16*config["pi_sigma"], maxv=32000),
                  "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                     length=4 * 16*config["pi_sigma"], maxv=32000),
                  "phase": 0, "gain": 0, "style": "arb",
              },
              "X/2": {
                  "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                 length=4 * 16*config["pi_sigma"], maxv=32000),
                  "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                     length=4 * 16*config["pi_sigma"], maxv=32000),
                  "phase": 0, "gain": config['pi_2_gain'], "style": "arb",
              },
            "-X/2": {
                "idata": -1 * gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                               length=4 * 16 * config["pi_sigma"], maxv=32000),
                "qdata": 0 * gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                                   length=4 * 16 * config["pi_sigma"], maxv=32000),
                "phase": 0, "gain": config['pi_2_gain'], "style": "arb",
            },
              "Y/2": {
                "idata": 0 * gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                               length=4 * 16 * config["pi_sigma"], maxv=32000),
                "qdata": gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                                   length=4 * 16 * config["pi_sigma"], maxv=32000),
                "phase": 0, "gain": config['pi_2_gain'], "style": "arb",
              },
            "-Y/2": {
                "idata": 0 * gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                                   length=4 * 16 * config["pi_sigma"], maxv=32000),
                "qdata": -1 * gauss(mu=16 * config["pi_sigma"] * 4 / 2, si=16 * config["pi_sigma"],
                               length=4 * 16 * config["pi_sigma"], maxv=32000),
                "phase": 0, "gain": config['pi_2_gain'], "style": "arb",
            },
              "Z/2": {
                  "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                 length=4 * 16*config["pi_sigma"], maxv=32000),
                  "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                     length=4 * 16*config["pi_sigma"], maxv=32000),
                  "phase": 0, "gain": 0, "style": "arb",
              },
              "-Z/2": {
                  "idata": gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                 length=4 * 16*config["pi_sigma"], maxv=32000),
                  "qdata": 0 * gauss(mu=16*config["pi_sigma"] * 4 / 2, si=16*config["pi_sigma"],
                                     length=4 * 16*config["pi_sigma"], maxv=32000),
                  "phase": 0, "gain": 0, "style": "arb",
              },
    }
