#! /usr/bin/env python
import argparse
import configparser
from collections import defaultdict, deque

from device import DeviceState
from events import EventType
from sim_interface import SimulatorBase, SimModule
from sim_modules import get_simulator_module
from utils import PriorityQueue

from trace_reader import get_trace_reader


class Priority:
    DEBUG_FIRST = 0
    ALARM = 5
    TRACE = 10
    DEBUG_LAST = 1024


class Simulator(SimulatorBase):
    EVENT_QUEUE_THRESHOLD = 100

    def __init__(self):
        self.sim_modules = {}
        self.module_type_map = defaultdict(deque)

        self.device_state = DeviceState()
        self.event_queue = PriorityQueue()

        self.current_time = None

        self.event_listeners = defaultdict(deque)
        self.trace_reader = None
        self.verbose = False
        self.debug_mode = False
        self.debug_interval = 1
        self.debug_interval_cnt = 0

    def has_module_instance(self, name):
        return name in self.sim_modules

    def get_module_instance(self, name):
        return self.sim_modules[name]

    def get_module_for_type(self, module_type):
        if module_type in self.module_type_map:
            return self.module_type_map[module_type.value][0]
        else:
            return None

    def register(self, sim_module, override=False):
        if not isinstance(sim_module, SimModule):
            raise TypeError("Expected SimModule object")

        if sim_module.get_name() in self.sim_modules:
            raise Exception("Module %s already exists" % sim_module.get_name())

        self.sim_modules[sim_module.get_name()] = sim_module

        if override:
            self.module_type_map[sim_module.get_type().value].appendleft(sim_module)
        else:
            self.module_type_map[sim_module.get_type().value].append(sim_module)

    def build(self, args):
        self.verbose = args.verbose
        self.debug_mode = args.debug

        # Instantiate necessary modules based on config files
        config = configparser.ConfigParser()
        config.read(args.sim_config)

        config['DEFAULT'] = {'modules': ''}

        if 'Simulator' not in config:
            raise Exception("Simulator section missing from config file")

        sim_settings = config['Simulator']
        modules_str = sim_settings['modules']
        if modules_str:
            modules_list = modules_str.split(' ')
        else:
            modules_list = []

        for module_name in modules_list:
            module_settings = {}
            if module_name in config:
                module_settings = config[module_name]

            self.register(get_simulator_module(module_name, self, module_settings))

        # Build list of modules
        for sim_module in self.sim_modules.values():
            sim_module.build()

    def run(self, trace_file):
        self.trace_reader = get_trace_reader(trace_file)
        self.trace_reader.build()

        # Check if we need to enter debug mode immediately
        if self.debug_mode:
            self.debug_interval_cnt = 0
            self.__debug()

        while not self.trace_reader.end_of_trace() \
                or not self.event_queue.empty():

            # Populate event queue if it is below the threshold number of events
            if self.event_queue.size() < Simulator.EVENT_QUEUE_THRESHOLD \
                    and not self.trace_reader.end_of_trace():
                self.__populate_event_queue_from_trace()
                continue

            # Look at next event to execute
            cur_event = self.event_queue.peek()

            # Look at next event from trace file
            trace_event = self.trace_reader.peek_event()

            # If trace event is supposed to occur before current
            # event, than we should populate event queue with more
            # events from the trace file
            if trace_event and cur_event.timestamp > trace_event.timestamp:
                self.__populate_event_queue_from_trace()
                continue

            self.event_queue.pop()

            # Set current time of simulator
            self.current_time = cur_event.timestamp
            if self.verbose:
                print(cur_event)

            if self.debug_mode:
                self.debug_interval_cnt += 1
                if self.debug_interval_cnt == self.debug_interval:
                    self.__debug()
                    self.debug_interval_cnt = 0

            self.__execute_event(cur_event)
        self.__finish()

    def subscribe(self, event_type, handler, event_filter=None):
        if event_type not in self.event_listeners:
            self.event_listeners[event_type] = []
        self.event_listeners[event_type].append((event_filter, handler))

    def broadcast(self, event):
        if event.timestamp:
            if event.timestamp != self.current_time:
                raise Exception("Broadcasting event with invalid timestamp.")
        else:
            event.timestamp = self.current_time

        # Get the set of listeners for the given event type
        listeners = self.event_listeners[event.event_type]
        for (event_filter, handler) in listeners:
            # Send event to each subscribed listener
            if not event_filter or event_filter(event):
                handler(event)

    def register_alarm(self, alarm):
        self.event_queue.push(alarm, (alarm.timestamp, Priority.ALARM))

    def get_current_time(self):
        return self.current_time

    def get_device_state(self):
        return self.device_state

    """
        Private method that handles execution of
        an event object.
    """
    def __execute_event(self, event):
        if event.event_type == EventType.SIM_DEBUG:
            self.__debug()
        elif event.event_type == EventType.SIM_ALARM:
            event.fire()
            if event.is_repeating():
                self.event_queue.push(event, (event.timestamp, Priority.ALARM))
        else:
            self.broadcast(event)

    def __populate_event_queue_from_trace(self):
        # Fill in event queue from trace
        events = self.trace_reader.get_events(count=Simulator.EVENT_QUEUE_THRESHOLD)
        for x in events:
            self.event_queue.push(x, (x.timestamp, Priority.TRACE))

    def __finish(self):
        # Call finish for all modules
        for sim_module in self.sim_modules.values():
            sim_module.finish()

    def __debug(self):
        while True:
            command = input("(uamp-sim debug) $ ")
            if command:
                tokens = command.split(sep=' ')
                cmd = tokens[0]
                args = tokens[1:]
                if cmd == 'quit' or cmd == 'exit' or cmd == 'q':
                    # TODO(dmanatunga): Handle simulation quitting better
                    print("Terminating Simulation")
                    exit(1)
                elif cmd == 'interval':
                    if len(args) == 1:
                        try:
                            self.debug_interval = int(args[0])
                        except ValueError:
                            print("Command Usage Error: interval command expects one numerical value")
                    else:
                        print("Command Usage Error: interval command expects one numerical value")
                elif cmd == 'verbose':
                    if len(args) == 0:
                        self.verbose = True
                    elif len(args) == 1:
                        if args[0] == 'on':
                            self.verbose = True
                        elif args[0] == 'off':
                            self.verbose = False
                        else:
                            print("Command Usage Error: verbose command expects 'on' or 'off' for argument")

                    else:
                        print("Command Usage Error: verbose command expects at most one argument")
            else:
                break


def parse_args():
    parser = argparse.ArgumentParser(description='Run uamp_sim')
    parser.add_argument('--trace', type=str, required=True,
                        help='User log trace file')
    parser.add_argument('--sim_config', type=str, required=True,
                        help='Sim Configuration File')
    parser.add_argument('-v,--verbose', dest='verbose', action='store_true',
                        default=False, help='Print out simulation run data')
    parser.add_argument('-D,--debug', dest='debug', action='store_true',
                        default=False, help='Run simulation in debug mode')
    return parser.parse_args()


def build_sim(args):
    simulator = Simulator()
    simulator.build(args)
    return simulator


if __name__ == "__main__":
    command_args = parse_args()
    sim = build_sim(command_args)
    sim.run(command_args.trace)
