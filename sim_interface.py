from abc import ABCMeta, abstractmethod
from enum import Enum, unique


@unique
class SimModuleType(Enum):
    PRELOAD_PREDICTOR = 'preload-predictor'
    REUSE_PREDICTOR = 'reuse-predictor'
    MEMORY_MANAGER = 'memory-manager'


class SimModule(metaclass=ABCMeta):
    def __init__(self, name, module_type, simulator):
        self.name = name
        self.module_type = module_type
        self.simulator = simulator
        self.collect_stats = False

    def get_name(self):
        return self.name

    def get_type(self):
        return self.module_type

    def enable_stats_collection(self):
        self.collect_stats = True

    def disable_stats_collection(self):
        self.collect_stats = False

    @abstractmethod
    def build(self):
        pass

    @abstractmethod
    def print_stats(self, output):
        pass

    @abstractmethod
    def finish(self):
        pass


class TraceReader(metaclass=ABCMeta):
    @abstractmethod
    def build(self):
        pass

    @abstractmethod
    def finish(self):
        pass

    @abstractmethod
    def peek_event(self):
        pass

    @abstractmethod
    def get_event(self):
        pass

    @abstractmethod
    def get_events(self, count):
        pass

    @abstractmethod
    def end_of_trace(self):
        pass

    @abstractmethod
    def get_start_time(self):
        pass

    @abstractmethod
    def get_end_time(self):
        pass


class SimulatorBase(metaclass=ABCMeta):
    @abstractmethod
    def build(self, config):
        pass

    @abstractmethod
    def get_module_for_type(self, module_type):
        pass

    @abstractmethod
    def has_module_instance(self, name):
        pass

    @abstractmethod
    def get_module_instance(self, name):
        pass

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def subscribe(self, event_type, handler, event_filter=None):
        pass

    @abstractmethod
    def broadcast(self, event):
        pass

    @abstractmethod
    def register_alarm(self, alarm):
        pass

    @abstractmethod
    def get_current_time(self):
        pass

    @abstractmethod
    def get_device_state(self):
        pass
