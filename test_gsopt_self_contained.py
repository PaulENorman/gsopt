import unittest
from unittest.mock import MagicMock, patch
import json
import io
import base64
import sys
import os
from unittest.mock import MagicMock

# -- MOCKING DEPENDENCIES BEFORE IMPORT --
# We mock numpy and other heavy libs so tests run without them installed
sys.modules['numpy'] = MagicMock()
# We assume flask is installed as it's the core framework, but if not, one would need to install it.
# sys.modules['flask'] = ... (Cannot mock flask easily as we need the real test client)

# Add current directory to path so we can import gsopt
sys.path.append(os.getcwd())

import gsopt

class TestGsOpt(unittest.TestCase):
    def setUp(self):
        self.app = gsopt.app.test_client()
        self.headers = {'X-User-Email': 'test@gmail.com'}
        # valid settings payload
        self.settings_payload = {
            "base_estimator": "GP",
            "acquisition_function": "EI",
            "acq_optimizer": "auto",
            "acq_func_kwargs": {},
            "num_params": 2,
            "param_names": ["x", "y"],
            "param_mins": [0.0, 0.0],
            "param_maxes": [1.0, 1.0],
            "num_init_points": 3,
            "batch_size": 2
        }

    def test_ping(self):
        response = self.app.post('/ping', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('timestamp', data)
        response = self.app.post('/ping', headers={})
        self.assertEqual(response.status_code, 403)

    def test_rate_limit(self):
        gsopt._rate_limit_storage['rate_test@gmail.com'] = []
        headers = {'X-User-Email': 'rate_test@gmail.com'}
        for _ in range(10):
            response = self.app.post('/ping', headers=headers)
            self.assertEqual(response.status_code, 200)
        response = self.app.post('/ping', headers=headers)
        self.assertEqual(response.status_code, 429)

    def test_test_connection(self):
        response = self.app.post('/test-connection', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['authenticated_user'], 'test@gmail.com')

    def test_init_optimization(self):
        from unittest.mock import MagicMock
        gsopt._ensure_optimizer_builder = lambda: None
        gsopt.OptimizerSettings = MagicMock()
        gsopt.OptimizerSettings.from_dict.return_value = MagicMock(num_init_points=3, param_names=["x", "y"])
        gsopt.build_skopt_optimizer = MagicMock()
        gsopt.build_skopt_optimizer.return_value.ask.return_value = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        payload = {"settings": self.settings_payload}
        response = self.app.post('/init-optimization', data=json.dumps(payload), content_type='application/json', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']), 3)
        self.assertEqual(data['data'][0]['x'], 0.1)
        self.assertEqual(data['data'][0]['y'], 0.2)

    def test_continue_optimization(self):
        from unittest.mock import MagicMock
        gsopt._ensure_optimizer_builder = lambda: None
        gsopt.OptimizerSettings = MagicMock()
        gsopt.OptimizerSettings.from_dict.return_value = MagicMock(batch_size=2, param_names=["x", "y"])
        gsopt.build_skopt_optimizer = MagicMock()
        gsopt.build_skopt_optimizer.return_value.ask.return_value = [[0.8, 0.9], [0.1, 0.0]]
        payload = {"settings": self.settings_payload, "existing_data": [{"x": 0.5, "y": 0.5, "objective": 0.1}]}
        response = self.app.post('/continue-optimization', data=json.dumps(payload), content_type='application/json', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data['data']), 2)

    def test_plot(self):
        from unittest.mock import MagicMock
        gsopt._ensure_matplotlib = lambda: None
        gsopt._ensure_skopt_plots = lambda: None
        gsopt._ensure_optimizer_builder = lambda: None
        gsopt.plt = MagicMock()
        gsopt.plot_convergence = MagicMock()
        gsopt.OptimizerSettings = MagicMock()
        gsopt.OptimizerSettings.from_dict.return_value = MagicMock(param_names=["x", "y"])
        gsopt.build_optimizer = MagicMock()
        mock_opt = MagicMock()
        mock_opt.optimizer.get_result.return_value.x_iters = [[1, 2]]
        gsopt.build_optimizer.return_value = mock_opt
        gsopt.plt.savefig.side_effect = lambda buf, **kwargs: buf.write(b'fake_png_data')
        payload = {"settings": self.settings_payload, "plot_type": "convergence", "existing_data": []}
        response = self.app.post('/plot', data=json.dumps(payload), content_type='application/json', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(len(data['plot_data']) > 0)
        gsopt.plot_convergence.assert_called()

if __name__ == '__main__':
    unittest.main()
