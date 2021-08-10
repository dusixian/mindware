import sys
import time
import traceback
from openbox.core.base import Observation
from openbox.utils.util_funcs import get_result
from mindware.utils.logging_utils import get_logger
from openbox.utils.constants import SUCCESS, FAILED, TIMEOUT
from openbox.utils.limit import time_limit, TimeoutException
from openbox.core.message_queue.worker_messager import WorkerMessager


class BaseWorker(object):
    def __init__(self, evaluator, ip, port, authkey):
        self.logger = get_logger(self.__module__ + "." + self.__class__.__name__)
        self.objective_function = evaluator
        self.worker_messager = WorkerMessager(ip, port, authkey)


class EvaluationWorker(BaseWorker):
    def __init__(self, evaluator, ip="127.0.0.1", port=13579, authkey=b'abc'):
        super().__init__(evaluator, ip, port, authkey)

    def run(self):
        while True:
            # Get config
            try:
                msg = self.worker_messager.receive_message()
            except Exception as e:
                self.logger.error("Worker receive message error: %s." % str(e))
                return
            if msg is None:
                # Wait for configs
                time.sleep(0.3)
                continue
            self.logger.info("Worker: get config. start working.")
            config, time_limit_per_trial = msg

            # Start working
            trial_state = SUCCESS
            start_time = time.time()
            try:
                args, kwargs = (config,), dict()
                timeout_status, _result = time_limit(self.objective_function,
                                                     time_limit_per_trial,
                                                     args=args, kwargs=kwargs)
                if timeout_status:
                    raise TimeoutException(
                        'Timeout: time limit for this evaluation is %.1fs' % time_limit_per_trial)
                else:
                    objs, constraints = get_result(_result)
            except Exception as e:
                if isinstance(e, TimeoutException):
                    trial_state = TIMEOUT
                else:
                    traceback.print_exc(file=sys.stdout)
                    trial_state = FAILED
                objs = None
                constraints = None

            elapsed_time = time.time() - start_time
            observation = Observation(config, trial_state, constraints, objs, elapsed_time)

            # Send result
            self.logger.info("Worker: observation=%s. sending result." % str(observation))
            try:
                self.worker_messager.send_message(observation)
            except Exception as e:
                self.logger.error("Worker send message error:", str(e))
                return
