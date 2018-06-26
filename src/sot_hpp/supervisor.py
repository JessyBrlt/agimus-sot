from __future__ import print_function
from tools import Manifold, Posture
from dynamic_graph.sot.core import SOT
from dynamic_graph import plug

def _hpTasks (sotrobot):
    return Manifold()
def _lpTasks (sotrobot):
    return Posture ("posture", sotrobot)

class Supervisor(object):
    """
    Steps: P = placement, G = grasp, p = pre-P, g = pre-G
    0. P <-> GP
    1. P <-> gP
    2. gP <-> GP
    3. GP <-> G
    4. GP <-> Gp
    5. Gp <-> G
    """
    def __init__ (self, sotrobot, lpTasks = None, hpTasks = None):
        self.sotrobot = sotrobot
        self.hpTasks = hpTasks if hpTasks is not None else _hpTasks(sotrobot)
        self.lpTasks = lpTasks if lpTasks is not None else _lpTasks(sotrobot)
        self.currentSot = None
        from dynamic_graph.sot.core.switch import SwitchVector
        self.sot_switch = SwitchVector ("sot_supervisor_switch")
        plug(self.sot_switch.sout, self.sotrobot.device.control)

    def setupEvents (self):
        from dynamic_graph.sot.core.operator import Norm_of_vector, CompareDouble
        from dynamic_graph.sot.core.event import Event
        from dynamic_graph.ros import RosPublish
        self.norm = Norm_of_vector ("control_norm")
        plug (self.sotrobot.device.control, self.norm.sin)

        self.norm_comparision = CompareDouble ("control_norm_comparison")
        plug (self.norm.sout, self.norm_comparision.sin1)
        self.norm_comparision.sin2.value = 1e-2

        self.norm_event = Event ("control_norm_event")
        plug (self.norm_comparision.sout, self.norm_event.condition)
        # self.sotrobot.device.after.addSignal (self.norm_event.check.name)
        self.sotrobot.device.after.addSignal ("control_norm_event.check")

        self.ros_publish = RosPublish ('ros_publish_control_norm')
        self.ros_publish.add ('double', 'event_control_norm', '/sot_hpp/control_norm_changed')
        plug (self.norm.sout, self.ros_publish.event_control_norm)
        # plug (self.norm_event.trigger, self.ros_publish.trigger)
        self.norm_event.addSignal ("ros_publish_control_norm.trigger")

    def makeInitialSot (self):
        # Create the initial sot (keep)
        sot = SOT ('sot_keep')
        sot.setSize(self.sotrobot.dynamic.getDimension())
        self.keep_posture = Posture ("posture_keep", self.sotrobot)
        self.keep_posture.tp.setWithDerivative (False)
        
        # TODO : I do agree that this is a dirty hack.
        # The COM of the robot in the HPP frame is at those coordinates (approx.).
        # But the keep_posture task is « internally » (there is no actuator able to directly move the COM, 
        # but the controller in the task is computing controls anyway, and integrating them) 
        # moving the computed COM to its reference value which is (0, 0, 0).
        # So, when we send the goal coordinates of the feet from HPP to the SoT, there is an offset of 0,74m
        # between the goal and the current position of the feet. This was the cause of the strange feet
        # movements at the beginning of the demo.
        # Maybe we can get the COM position and orientation from HPP at the beginning of the trajectory
        # to initialize self.sotrobot.dynamic.position.value
        # self.keep_posture._signalPositionRef().value = tuple([-0.74, 0.0, 1.0, 0.0, 0.0, 0.0] + list(self.sotrobot.dynamic.position.value)[6:])

        # The above TODO must be fixed in users script by providing the
        # right initial pose using robot.device.set (configuration) before starting
        # dynamic graph.
        self.keep_posture._signalPositionRef().value = self.sotrobot.dynamic.position.value
        
        self.keep_posture.pushTo(sot)
        self.addSot ("", sot, sot.control)

    def addSot (self, name, sot, controlSignal):
        self.sots[name] = sot
        self.addSignalToSotSwitch (sot.name, controlSignal)

    def addSignalToSotSwitch (self, name, controlSignal):
        n = self.sot_switch.getSignalNumber()
        self.sot_switch.setSignalNumber(n+1)
        self.sots_indexes[name] = n
        plug (controlSignal, self.sot_switch.signal("sin" + str(n)))

    def topics (self):
        c = self.hpTasks + self.lpTasks
        for g in self.grasps.values():
            c += g

        return c.topics

    def plugTopicsToRos (self):
        from dynamic_graph.ros.ros_queued_subscribe import RosQueuedSubscribe
        self.rosSusbcribe = RosQueuedSubscribe ('ros_queued_subscribe')
        from dynamic_graph.ros.ros_tf_listener import RosTfListener
        self.rosTf = RosTfListener ('ros_tf_listener')
        topics = self.topics()

        for name, topic_info in topics.items():
            topic_handler = _handlers[topic_info.get("handler","default")]
            topic_handler (name,topic_info,self.rosSusbcribe,self.rosTf)

    def isSotConsistentWithCurrent(self, transitionName, thr = 1e-3):
        if self.currentSot is None or transitionName == self.currentSot:
            return True
        csot = self.sots[self.currentSot]
        nsot = self.sots[transitionName]
        t = self.sotrobot.device.control.time
        # This is not safe since it would be run concurrently with the
        # real time thread.
        csot.control.recompute(t)
        nsot.control.recompute(t)
        from numpy import array, linalg
        error = array(nsot.control.value) - array(csot.control.value)
        n = linalg.norm(error)
        if n > thr:
            print ("Control not consistent:", linalg.norm(error),'\n', error)
            return False
        return True

    def clearQueues(self):
        exec ("tmp = " + self.rosSusbcribe.list())
        for s in tmp:
            self.rosSusbcribe.clearQueue(s)

    def readQueue(self, read):
        if read < 0:
            print ("ReadQueue argument should be >= 0")
            return
        t = self.sotrobot.device.control.time
        self.rosSusbcribe.readQueue (t + read)

    def stopReadingQueue(self):
        self.rosSusbcribe.readQueue (-1)

    def plugSot(self, transitionName, check = False):
        if check and not self.isSotConsistentWithCurrent (transitionName):
            # raise Exception ("Sot %d not consistent with sot %d" % (self.currentSot, id))
            print("Sot {0} not consistent with sot {1}".format(self.currentSot, transitionName))
        if transitionName == "":
            # TODO : Explanation and linked TODO in the function makeInitialSot
            self.keep_posture._signalPositionRef().value = self.sotrobot.dynamic.position.value
        sot = self.sots[transitionName]
        n = self.sots_indexes[sot.name]
        # Start reading queues
        self.readQueue(10)
        self.sot_switch.selection.value = n
        print("Current sot:", transitionName, "\n", sot.display())
        self.currentSot = transitionName

    def runPreAction(self, transitionName):
        if self.preActions.has_key(transitionName):
            sot = self.preActions[transitionName]
            print("Running pre action", transitionName,
                    "\n", sot.display())
            # t = self.sotrobot.device.control.time
            # This is not safe since it would be run concurrently with the
            # real time thread.
            # sot.control.recompute(t-1)
            n = self.sots_indexes[sot.name]
            self.sot_switch.selection.value = n
            return
        print ("No pre action", transitionName)

    def runPostAction(self, targetStateName):
        if self.postActions.has_key(self.currentSot):
            d = self.postActions[self.currentSot]
            if d.has_key(targetStateName):
                sot = d[targetStateName]
                print( "Running post action", self.currentSot, targetStateName,
                    "\n", sot.display())
                # t = self.sotrobot.device.control.time
                # This is not safe since it would be run concurrently with the
                # real time thread.
                # sot.control.recompute(t-1)
                n = self.sots_indexes[sot.name]
                self.sot_switch.selection.value = n
                return
        print ("No post action", self.currentSot, targetStateName)

    def getJointList (self, prefix = ""):
        return [ prefix + n for n in self.sotrobot.dynamic.model.names[1:] ]

    def publishState (self, subsampling = 40):
        if hasattr (self, "ros_publish_state"):
            return
        from dynamic_graph.ros import RosPublish
        self.ros_publish_state = RosPublish ("ros_publish_state")
        self.ros_publish_state.add ("vector", "state", "/sot_hpp/state")
        self.ros_publish_state.add ("vector", "reference_state", "/sot_hpp/reference_state")
        plug (self.sotrobot.device.state, self.ros_publish_state.state)
        plug (self.rosSusbcribe.posture, self.ros_publish_state.reference_state)
        self.sotrobot.device.after.addDownsampledSignal ("ros_publish_state.trigger", subsampling)

def _defaultHandler(name,topic_info,rosSusbcribe,rosTf):
    topic = topic_info["topic"]
    rosSusbcribe.add (topic_info["type"], name, topic)
    for s in topic_info['signalGetters']:
        plug (rosSusbcribe.signal(name), s())
    print (topic, "plugged to", name, ', ', len(topic_info['signalGetters']), 'times')

def _handleTfListener (name,topic_info,rosSusbcribe,rosTf):
    signame = topic_info["frame1"] + "_wrt_" + topic_info["frame0"]
    rosTf.add (topic_info["frame0"], topic_info["frame1"], signame)
    for s in topic_info['signalGetters']:
        plug (rosTf.signal(signame), s())
    print (topic_info["frame1"], "wrt", topic_info["frame0"], "plugged to", signame, ', ', len(topic_info['signalGetters']), 'times')

def _handleHppJoint (name,topic_info,rosSusbcribe,rosTf):
    if topic_info["velocity"]: topic = "velocity/op_frame"
    else:                      topic = "op_frame"
    ti = dict(topic_info)
    ti["topic"] = "/hpp/target/" + topic + '/' + topic_info['hppjoint']
    _defaultHandler (name,ti,rosSusbcribe,rosTf)

def _handleHppCom (name,topic_info,rosSusbcribe,rosTf):
    if topic_info["velocity"]: topic = "velocity/com"
    else:                      topic = "com"
    ti = dict(topic_info)
    if topic_info['hppcom'] == "":
        ti["topic"] = "/hpp/target/" + topic
    else:
        ti["topic"] = "/hpp/target/" + topic + '/' + topic_info['hppcom']
    _defaultHandler (name,ti,rosSusbcribe,rosTf)

_handlers = {
        "hppjoint": _handleHppJoint,
        "hppcom": _handleHppCom,
        "tf_listener": _handleTfListener,
        "default": _defaultHandler,
        }
