from dynamic_graph import plug
from dynamic_graph.sot.core.integrator_euler import IntegratorEulerVectorMatrix
import dynamic_graph.sot.core as dgsc
import sot_hpp.control.controllers as controllers
import numpy as np
from math import sqrt, pi

import matplotlib
import matplotlib.pyplot as plt

### Parameters
# {{{

# Torque amplitude
A_torque = 5.

## Measurement model (for simulation)
M = 0.5
# M = 0.001
# M = 0.
d = 10.
k = 100.

# The angle at which a contact is created.
theta0 = 1.
# theta0 = 40. * pi / 180.
# theta0 = 1. * pi / 180.
# theta0 = 0

## Estimated model (not used except est_theta0)
est_M = M
est_d = d
est_k = k
# Use for the initial position control. It should be greater than theta0
# so that position control will run until the object is touched.
est_theta0 = theta0 + 10. * pi / 180.
# est_theta0 = theta0 + 1. * pi / 180.
# est_theta0 = theta0 - 10. * pi / 180.

# Time step and duration of simulation
dt = 0.001
# N = int(50 / dt)
# N = int(10 / dt)
N = int(1.5 / dt)
# N = int(0.5 / dt)
# N = 30
# }}}

### Measurements (Feedback)
# {{{

## omega -> theta
omega2theta = IntegratorEulerVectorMatrix ("omega2theta")
omega2theta.pushDenomCoef(((0,),))
omega2theta.pushDenomCoef(((1,),))
omega2theta.pushNumCoef(((1,),))

omega2theta.sin.value = (0,)
omega2theta.initialize()
omega2theta.setSamplingPeriod(dt)

## theta -> phi = theta - theta0
theta2phi = dgsc.Add_of_vector("theta2phi")
theta2phi.setCoeff1 ( 1)
theta2phi.setCoeff2 (-1)
theta2phi.sin2.value = (theta0,)
# theta2phi.sin1 <- theta

## phi -> torque
phi2torque = IntegratorEulerVectorMatrix ("phi2torque")
phi2torque.pushDenomCoef(((1,),))
phi2torque.pushNumCoef(((k,),))
phi2torque.pushNumCoef(((d,),))
if M != 0: phi2torque.pushNumCoef(((M,),))

phi2torque.sin.value = (0,)
phi2torque.initialize()
phi2torque.setSamplingPeriod(dt)

## Plug signals
plug (omega2theta.sout, theta2phi.sin1)
plug (theta2phi.sout  , phi2torque.sin)
# }}}

### Feed-forward - non-contact phase
# {{{

# z  = 0
# z  = sqrt(2)/2
z  = 1
# z  = 5
# wn = 0.1
# wn = 1.
wn = 10.

# the control reaches a precision of 5% at
# z = 1: t = - log(0.05) / wn
# z < 1: t = - log(0.05 * sqrt(1-z**2)) / (z * wn),

print "Non-contact phase - PID:"
print " - z  =", z
print " - wn =", wn

pos_control = controllers.secondOrderClosedLoop ("position_controller", wn, z, dt, (0,))
pos_control.reference.value = (est_theta0,)

# }}}

### Feed-forward - contact phase
# {{{

# dY/dt + Y = X
# tau = 0.1
tau = 1.
# tau = 10.

# alpha_m, alpha_M = root_second_order(4*z**2 * est_M * k - d**2, 4*z**2*tau*k - 2*d, 1)
# alpha = alpha_m if alpha_m > 0 else alpha_M
# alpha = min (max(0.5, alpha), 1.5)
alpha = 1.
# alpha = 10.

print "Contact phase - PD:"
print " - tau   =", tau
# print " - alpha_m =", alpha_m
# print " - alpha_M =", alpha_M
print " - alpha =", alpha
denom = alpha * M + tau
print " - beta  1 =", alpha / denom
print " - alpha 0 =", alpha * k / denom
print " - alpha 1 =", (1+alpha*d)/denom
print " - alpha 2 =", 1

torque_controller = controllers.Controller ("torque_controller", (alpha,), (1., tau), dt, (0,))
torque_controller.addFeedback()

# }}}

### Input
# {{{

def sinus (t):
    from math import cos, sin, pi
    T = 0.5
    return (A_torque * (1. + 0.1 * sin(2 * pi / T * t)),)

def constant (t):
    return (A_torque,)

input = constant
# input = sinus
# }}}

### Stability study
# {{{

# }}}

### Setup switch between the two control scheme
# {{{

from sot_hpp.control.switch import ControllerSwitch

switch = ControllerSwitch ("controller_switch",
        (pos_control.outputDerivative, torque_controller.output),
        (1e-5,))

plug(switch.signalOut, omega2theta.sin)

# }}}

### Simulation
# {{{

t = 1
ts=[]
inputs=[]
conditions=[]
thetas=[]
omegas=[]
torques=[]

phi = - theta0
torque_control = False

theta = 0.

for i in range(1,N):
    input_torque = input(t * dt)
    if phi < 0:
        if torque_control:
            print "Loosing contact at time", t
            # measured_torque = (1e-4,)
        # else:
        measured_torque = (0,)
    else:
        measured_torque = phi2torque.sout.value
        if len(measured_torque) != 1:
            print "Assuming very small measured torque at", t, phi
            measured_torque = (1e-4,)

    if pos_control.hasFeedback:
        pos_control.measurement.value = (theta,)

    torque_controller.reference  .value = input_torque
    torque_controller.measurement.value = measured_torque
    switch.measurement.value = measured_torque

    switch.event.check.recompute(t)
    phi2torque.sout.recompute(t);

    if not torque_control and switch.latch.out.value == 1:
        # Switch to torque control
        print "Switch to torque control at", t
        torque_control = True
    elif torque_control and switch.latch.out.value == 0:
        print "Switch to position control at", t
        torque_control = False

    ts     .append(t * dt)
    conditions.append(switch.latch.out.value)
    inputs .append(input_torque)
    omegas .append(omega2theta.sin.value[0])
    thetas .append(omega2theta.sout.value[0])
    torques.append(measured_torque)

    theta = omega2theta.sout.value[0]
    phi = theta2phi.sout.value[0]
    t += 1

# }}}

### Plot the results
# {{{

skip=0

plt.subplot(2,1,1)
plt.plot(ts[skip:], inputs[skip:], 'b', ts[skip:], torques[skip:], 'g',
        ts[skip:], conditions[skip:], 'r'
        )
plt.legend(["Reference torque", "Measured torque"
    ,"Torque control active"
    ])
plt.grid()

plt.subplot(2,1,2)
plt.plot([ts[skip],ts[-1]], [theta0,theta0], "b",
         [ts[skip],ts[-1]], [est_theta0,est_theta0], "k--",
         ts[skip:], thetas[skip:], 'r',
         ts[skip:], omegas[skip:], 'g +')
plt.legend(["theta_0", "Estimated theta_0", "Angle", "Velocity"])
plt.grid()

plt.show()

# }}}

# vim: set foldmethod=marker:
