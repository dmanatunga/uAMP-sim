#! /usr/bin/env python
import argparse
from collections import defaultdict, deque

from device import DeviceState
from sim_interface import SimulatorBase, SimModule
from utils import PriorityQueue

from trace_reader import get_trace_reader


class Simulator(SimulatorBase):
    EVENT_QUEUE_THRESHOLD = 100

    def __init__(self):
        self.modules = {}
        self.module_type_map = defaultdict(deque)

        self.device_state = DeviceState()
        self.event_queue = PriorityQueue()
        self.alarms = []
        self.modules = {}
        self.event_listeners = defaultdict(deque)
        self.trace_reader = None
        self.verbose = False
        self.debug_mode = False
        self.debug_interval = 1
        self.debug_interval_cnt = 0

    def register(self, sim_module, override=False):
        if not isinstance(sim_module, SimModule):
            raise TypeError("Expected SimModule object")

        if sim_module.get_name() in self.modules:
            raise Exception("Module %s already exists" % sim_module.get_name())

        self.modules[sim_module.get_name()] = sim_module

        if override:
            self.module_type_map[sim_module.get_type()].appendleft(sim_module)
        else:
            self.module_type_map[sim_module.get_type()].append(sim_module)

    def has_module_instance(self, name):
        return name in self.modules

    def get_module_instance(self, name):
        return self.modules[name]

    def get_module_for_type(self, module_type):
        if module_type in self.module_type_map:
            return self.module_type_map[module_type][0]
        else:
            return None

    def build(self, args):
        self.verbose = args.verbose
        self.debug_mode = args.debug
        # Instantiate necessary modules based on config files

        # Build list of modules
        for module in self.modules.values():
            module.build()

    def run(self, trace_file):
        self.trace_reader = get_trace_reader(trace_file)
        self.trace_reader.build()

        if self.debug_mode:
            self.debug_interval_cnt = 0
            self.debug()

        while not self.trace_reader.end_of_trace() or not self.event_queue.empty():
            # Populate event queue if it is below the threshold number of events
            if self.event_queue.size() < Simulator.EVENT_QUEUE_THRESHOLD \
                    and not self.trace_reader.end_of_trace():
                self.populate_event_queue_from_trace()
                continue

            cur_event = self.event_queue.peek()
            trace_event = self.trace_reader.peek_event()
            if trace_event and cur_event.timestamp > trace_event.timestamp:
                self.populate_event_queue_from_trace()
                continue

            self.event_queue.pop()
            if self.verbose:
                print(cur_event)

            if self.debug_mode:
                self.debug_interval_cnt += 1
                if self.debug_interval_cnt == self.debug_interval:
                    self.debug()
                    self.debug_interval_cnt = 0

            self.broadcast(cur_event)
        self.finish()

    def populate_event_queue_from_trace(self):
        # Fill in event queue from trace
        events = self.trace_reader.get_events(count=Simulator.EVENT_QUEUE_THRESHOLD)
        [self.event_queue.push(x) for x in events]

    def finish(self):
        # Call finish for all modules
        for module in self.modules.values():
            module.finish()

    def subscribe(self, event_type, callback, event_filter=None):
        if event_type not in self.event_listeners:
            self.event_listeners[event_type] = []
        self.event_listeners[event_type].append((event_filter, callback))

    def broadcast(self, event):
        # Get the set of listeners for the given event type
        listeners = self.event_listeners[event.event_type]
        for (event_filter, callback) in listeners:
            # Send event to each subscribed listener
            if not event_filter or event_filter(event):
                callback(event)

    def register_alarm(self, alarm, callback):
        pass

    def debug(self):
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
    parser.add_argument('--sim_config', type=str, required=False,
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
