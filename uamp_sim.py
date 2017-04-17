#! /usr/bin/env python
import argparse
import configparser
from collections import defaultdict, deque

import sys
import datetime

from device import DeviceState
from events import EventType, SimAlarm
from sim_interface import SimulatorBase, SimModule
from sim_modules import get_simulator_module
from utils import PriorityQueue

from trace_reader import get_trace_reader


class Priority:
    DEBUG_FIRST = 0
    SIMULATOR = 1
    ALARM = 5
    TRACE = 10
    DEBUG_LAST = 1024


class Simulator(SimulatorBase):
    EVENT_QUEUE_THRESHOLD = 100

    def __init__(self):
        self._sim_modules = {}
        self._module_type_map = defaultdict(deque)

        self._device_state = DeviceState()
        self._event_queue = PriorityQueue()

        self._current_time = None
        self._warmup_period = None

        self._event_listeners = defaultdict(deque)
        self._trace_reader = None
        self._trace_executed = False
        self._verbose = False
        self._debug_mode = False
        self._debug_interval = 1
        self._debug_interval_cnt = 0

    def has_module_instance(self, name):
        return name in self._sim_modules

    def get_module_instance(self, name):
        return self._sim_modules[name]

    def get_module_for_type(self, module_type):
        if module_type in self._module_type_map:
            return self._module_type_map[module_type.value][0]
        else:
            return None

    def register(self, sim_module, override=False):
        if not isinstance(sim_module, SimModule):
            raise TypeError("Expected SimModule object")

        if sim_module.get_name() in self._sim_modules:
            raise Exception("Module %s already exists" % sim_module.get_name())

        self._sim_modules[sim_module.get_name()] = sim_module

        if override:
            self._module_type_map[sim_module.get_type().value].appendleft(sim_module)
        else:
            self._module_type_map[sim_module.get_type().value].append(sim_module)

    def build(self, args):
        self._verbose = args.verbose
        self._debug_mode = args.debug

        # Instantiate necessary modules based on config files
        config = configparser.ConfigParser()
        config.read(args.sim_config)

        config['DEFAULT'] = {'modules': '', 'warmup_period': ''}

        if 'Simulator' not in config:
            raise Exception("Simulator section missing from config file")

        sim_settings = config['Simulator']

        # Identify the set of modules to include
        modules_str = sim_settings['modules']
        if modules_str:
            modules_list = modules_str.split(' ')
        else:
            modules_list = []

        self._warmup_period = \
            self.__parse_warmup_setting(sim_settings['warmup_period'])

        # Setup the trace file reader and initial simulator time
        self._trace_reader = get_trace_reader(args.trace)
        self._trace_reader.build()
        self._trace_executed = False
        self._current_time = self._trace_reader.get_start_time()

        for module_name in modules_list:
            module_settings = {}
            if module_name in config:
                module_settings = config[module_name]

            self.register(get_simulator_module(module_name, self, module_settings))

        # Build list of modules
        for sim_module in self._sim_modules.values():
            sim_module.build()

    def run(self):
        # Check if we need to enter debug mode immediately
        if self._debug_mode:
            self._debug_interval_cnt = 0
            self.__debug()

        # Add alarm event for the warmup period
        warmup_finish_alarm = SimAlarm(
            timestamp=self._trace_reader.get_start_time() + self._warmup_period,
            handler=self.__enable_stats_collection,
            name='Warmup Period Alarm')
        self._event_queue.push(warmup_finish_alarm,
                               (warmup_finish_alarm.timestamp, Priority.SIMULATOR))

        while not self._trace_reader.end_of_trace() \
                or not self._event_queue.empty():

            # Populate event queue if it is below the threshold number of events
            if self._event_queue.size() < Simulator.EVENT_QUEUE_THRESHOLD \
                    and not self._trace_reader.end_of_trace():
                self.__populate_event_queue_from_trace()
                continue

            # Look at next event to execute
            cur_event = self._event_queue.peek()

            # Look at next event from trace file
            trace_event = self._trace_reader.peek_event()

            # If trace event is supposed to occur before current
            # event, than we should populate event queue with more
            # events from the trace file
            if trace_event and cur_event.timestamp > trace_event.timestamp:
                self.__populate_event_queue_from_trace()
                continue

            self._event_queue.pop()

            # Set current time of simulator
            self._current_time = cur_event.timestamp
            if self._verbose:
                print(cur_event)

            if self._debug_mode:
                self._debug_interval_cnt += 1
                if self._debug_interval_cnt == self._debug_interval:
                    self.__debug()
                    self._debug_interval_cnt = 0

            self.__execute_event(cur_event)
        self.__finish()

    def subscribe(self, event_type, handler, event_filter=None):
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append((event_filter, handler))

    def broadcast(self, event):
        if event.timestamp:
            if event.timestamp != self._current_time:
                raise Exception("Broadcasting event with invalid timestamp.")
        else:
            event.timestamp = self._current_time

        # Get the set of listeners for the given event type
        listeners = self._event_listeners[event.event_type]
        for (event_filter, handler) in listeners:
            # Send event to each subscribed listener
            if not event_filter or event_filter(event):
                handler(event)

    def register_alarm(self, alarm):
        self._event_queue.push(alarm, (alarm.timestamp, Priority.ALARM))

    def get_current_time(self):
        return self._current_time

    def get_device_state(self):
        return self._device_state

    def __parse_warmup_setting(self, setting_value):
        if setting_value:
            if setting_value.endswith('h'):
                num_hours = int(setting_value[:-1])
                return datetime.timedelta(hours=num_hours)
            raise Exception("Invalid warmup period setting format")
        else:
            return datetime.timedelta()

    def __enable_stats_collection(self):
        for sim_module in self._sim_modules.values():
            sim_module.enable_stats_collection()

    def __disable_stats_collection(self):
        for sim_module in self._sim_modules.values():
            sim_module.disable_stats_collection()

    """
        Private method that handles execution of
        an event object.
    """
    def __execute_event(self, event):
        if event.event_type == EventType.SIM_DEBUG:
            self.__debug()
        elif event.event_type == EventType.SIM_ALARM:
            if not self._trace_executed:
                event.fire()
                if event.is_repeating():
                    self._event_queue.push(event, (event.timestamp, Priority.ALARM))
        elif event.event_type == EventType.TRACE_END:
            self._trace_executed = True
        else:
            self.broadcast(event)

    def __populate_event_queue_from_trace(self):
        # Fill in event queue from trace
        events = self._trace_reader.get_events(count=Simulator.EVENT_QUEUE_THRESHOLD)
        for x in events:
            self._event_queue.push(x, (x.timestamp, Priority.TRACE))

    def __finish(self):
        output_file = sys.stdout
        # Print status from all modules
        for sim_module in self._sim_modules.values():
            header = "======== %s Stats ========\n" % sim_module.get_name()
            footer = "=" * (len(header) - 1) + '\n'
            output_file.write(header)
            sim_module.print_stats(output_file)
            output_file.write(footer)

        # Call finish for all modules
        for sim_module in self._sim_modules.values():
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
                            self._debug_interval = int(args[0])
                        except ValueError:
                            print("Command Usage Error: interval command expects one numerical value")
                    else:
                        print("Command Usage Error: interval command expects one numerical value")
                elif cmd == 'verbose':
                    if len(args) == 0:
                        self._verbose = True
                    elif len(args) == 1:
                        if args[0] == 'on':
                            self._verbose = True
                        elif args[0] == 'off':
                            self._verbose = False
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
    sim.run()
