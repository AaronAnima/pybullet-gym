from .robot_bases import XmlBasedRobot, MJCFBasedRobot, URDFBasedRobot
import numpy as np
from ..utils import gym_utils as ObjectHelper
import pybullet as p


class WalkerBase(XmlBasedRobot):
	def __init__(self, power):
		self.power = power
		self.camera_x = 0
		self.start_pos_x, self.start_pos_y, self.start_pos_z = 0, 0, 0
		self.walk_target_x = 1e3  # kilometer away
		self.walk_target_y = 0

	def robot_specific_reset(self):
		for j in self.ordered_joints:
			j.reset_current_position(self.np_random.uniform(low=-0.1, high=0.1), 0)

		self.feet = [self.parts[f] for f in self.foot_list]
		self.feet_contact = np.array([0.0 for f in self.foot_list], dtype=np.float32)
		self.scene.actor_introduce(self)
		self.initial_z = None

	def apply_action(self, a):
		assert (np.isfinite(a).all())
		for n, j in enumerate(self.ordered_joints):
			j.set_motor_torque(self.power * j.power_coef * float(np.clip(a[n], -1, +1)))

	def calc_state(self):
		j = np.array([j.current_relative_position() for j in self.ordered_joints], dtype=np.float32).flatten()
		# even elements [0::2] position, scaled to -1..+1 between limits
		# odd elements  [1::2] angular speed, scaled to show -1..+1
		self.joint_speeds = j[1::2]
		self.joints_at_limit = np.count_nonzero(np.abs(j[0::2]) > 0.99)

		body_pose = self.robot_body.pose()
		parts_xyz = np.array([p.pose().xyz() for p in self.parts.values()]).flatten()
		self.body_xyz = (
		parts_xyz[0::3].mean(), parts_xyz[1::3].mean(), body_pose.xyz()[2])  # torso z is more informative than mean z
		self.body_rpy = body_pose.rpy()
		z = self.body_xyz[2]
		if self.initial_z == None:
			self.initial_z = z
		r, p, yaw = self.body_rpy
		self.walk_target_theta = np.arctan2(self.walk_target_y - self.body_xyz[1],
											self.walk_target_x - self.body_xyz[0])
		self.walk_target_dist = np.linalg.norm(
			[self.walk_target_y - self.body_xyz[1], self.walk_target_x - self.body_xyz[0]])
		angle_to_target = self.walk_target_theta - yaw

		rot_speed = np.array(
			[[np.cos(-yaw), -np.sin(-yaw), 0],
			 [np.sin(-yaw), np.cos(-yaw), 0],
			 [		0,			 0, 1]]
		)
		vx, vy, vz = np.dot(rot_speed, self.robot_body.speed())  # rotate speed back to body point of view

		more = np.array([ z-self.initial_z,
			np.sin(angle_to_target), np.cos(angle_to_target),
			0.3* vx , 0.3* vy , 0.3* vz ,  # 0.3 is just scaling typical speed into -1..+1, no physical sense here
			r, p], dtype=np.float32)
		return np.clip( np.concatenate([more] + [j] + [self.feet_contact]), -5, +5)

	def calc_potential(self):
		# progress in potential field is speed*dt, typical speed is about 2-3 meter per second, this potential will change 2-3 per frame (not per second),
		# all rewards have rew/frame units and close to 1.0
		return - self.walk_target_dist / self.scene.dt


class Hopper(WalkerBase , MJCFBasedRobot):
	foot_list = ["foot"]

	def __init__(self):
		WalkerBase.__init__(self, power=0.75)
		MJCFBasedRobot.__init__(self, "hopper.xml", "torso", action_dim=3, obs_dim=15)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.8 and abs(pitch) < 1.0 else -1


class Walker2D(WalkerBase, MJCFBasedRobot):
	foot_list = ["foot", "foot_left"]

	def __init__(self):
		WalkerBase.__init__(self, power=0.40)
		MJCFBasedRobot.__init__(self, "walker2d.xml", "torso", action_dim=6, obs_dim=22)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.8 and abs(pitch) < 1.0 else -1

	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)
		for n in ["foot_joint", "foot_left_joint"]:
			self.jdict[n].power_coef = 30.0


class HalfCheetah(WalkerBase, MJCFBasedRobot):
	foot_list = ["ffoot", "fshin", "fthigh",  "bfoot", "bshin", "bthigh"]  # track these contacts with ground

	def __init__(self):
		WalkerBase.__init__(self, power=0.90)
		MJCFBasedRobot.__init__(self, "half_cheetah.xml", "torso", action_dim=6, obs_dim=26)

	def alive_bonus(self, z, pitch):
		# Use contact other than feet to terminate episode: due to a lot of strange walks using knees
		return +1 if np.abs(pitch) < 1.0 and not self.feet_contact[1] and not self.feet_contact[2] and not self.feet_contact[4] and not self.feet_contact[5] else -1

	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)
		self.jdict["bthigh"].power_coef = 120.0
		self.jdict["bshin"].power_coef  = 90.0
		self.jdict["bfoot"].power_coef  = 60.0
		self.jdict["fthigh"].power_coef = 140.0
		self.jdict["fshin"].power_coef  = 60.0
		self.jdict["ffoot"].power_coef  = 30.0


class Ant(WalkerBase, MJCFBasedRobot):
	foot_list = ['front_left_foot', 'front_right_foot', 'left_back_foot', 'right_back_foot']

	def __init__(self):
		WalkerBase.__init__(self, power=10.5)
		MJCFBasedRobot.__init__(self, "ant.xml", "torso", action_dim=8, obs_dim=28)

	def alive_bonus(self, z, pitch):
		return +1 if z > 0.26 else -1  # 0.25 is central sphere rad, die if it scrapes the ground


class Humanoid(WalkerBase, MJCFBasedRobot):
	self_collision = True
	foot_list = ["right_foot", "left_foot"]  # "left_hand", "right_hand"

	def __init__(self):
		WalkerBase.__init__(self, power=0.41)
		MJCFBasedRobot.__init__(self, 'humanoid_symmetric.xml', 'torso', action_dim=17, obs_dim=44)
		# 17 joints, 4 of them important for walking (hip, knee), others may as well be turned off, 17/4 = 4.25

	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)
		self.motor_names  = ["abdomen_z", "abdomen_y", "abdomen_x"]
		self.motor_power  = [100, 100, 100]
		self.motor_names += ["right_hip_x", "right_hip_z", "right_hip_y", "right_knee"]
		self.motor_power += [100, 100, 300, 200]
		self.motor_names += ["left_hip_x", "left_hip_z", "left_hip_y", "left_knee"]
		self.motor_power += [100, 100, 300, 200]
		self.motor_names += ["right_shoulder1", "right_shoulder2", "right_elbow"]
		self.motor_power += [75, 75, 75]
		self.motor_names += ["left_shoulder1", "left_shoulder2", "left_elbow"]
		self.motor_power += [75, 75, 75]
		self.motors = [self.jdict[n] for n in self.motor_names]
		# if self.random_yaw: # TODO: Make leaning work as soon as the rest works
		# 	cpose = cpp_household.Pose()
		# 	yaw = self.np_random.uniform(low=-3.14, high=3.14)
		# 	if self.random_lean and self.np_random.randint(2)==0:
		# 		cpose.set_xyz(0, 0, 1.4)
		# 		if self.np_random.randint(2)==0:
		# 			pitch = np.pi/2
		# 			cpose.set_xyz(0, 0, 0.45)
		# 		else:
		# 			pitch = np.pi*3/2
		# 			cpose.set_xyz(0, 0, 0.25)
		# 		roll = 0
		# 		cpose.set_rpy(roll, pitch, yaw)
		# 	else:
		# 		cpose.set_xyz(0, 0, 1.4)
		# 		cpose.set_rpy(0, 0, yaw)  # just face random direction, but stay straight otherwise
		# 	self.cpp_robot.set_pose_and_speed(cpose, 0,0,0)
		self.initial_z = 0.8

	random_yaw = False
	random_lean = False

	def apply_action(self, a):
		assert( np.isfinite(a).all() )
		force_gain = 1
		for i, m, power in zip(range(17), self.motors, self.motor_power):
			m.set_motor_torque( float(force_gain * power*self.power*a[i]) )
			#m.set_motor_torque(float(force_gain * power * self.power * np.clip(a[i], -1, +1)))

	def alive_bonus(self, z, pitch):
		return +2 if z > 0.78 else -1   # 2 here because 17 joints produce a lot of electricity cost just from policy noise, living must be better than dying


class HumanoidFlagrun(Humanoid):
	def __init__(self):
		Humanoid.__init__(self)

	def robot_specific_reset(self):
		Humanoid.robot_specific_reset(self)
		self.flag_reposition()

	def flag_reposition(self):
		self.walk_target_x = self.np_random.uniform(low=-self.scene.stadium_halflen,   high=+self.scene.stadium_halflen)
		self.walk_target_y = self.np_random.uniform(low=-self.scene.stadium_halfwidth, high=+self.scene.stadium_halfwidth)
		more_compact = 0.5  # set to 1.0 whole football field
		self.walk_target_x *= more_compact
		self.walk_target_y *= more_compact
		self.flag = None
		self.flag = ObjectHelper.get_sphere(self.walk_target_x, self.walk_target_y, 0.2)
		self.flag_timeout = 200

	def calc_state(self):
		self.flag_timeout -= 1
		state = Humanoid.calc_state(self)
		if self.walk_target_dist < 1 or self.flag_timeout <= 0:
			self.flag_reposition()
			state = Humanoid.calc_state(self)  # caclulate state again, against new flag pos
			self.potential = self.calc_potential()	   # avoid reward jump
		return state


class HumanoidFlagrunHarder(HumanoidFlagrun):
	def __init__(self):
		HumanoidFlagrun.__init__()

	def robot_specific_reset(self):
		HumanoidFlagrun.robot_specific_reset(self)
		self.aggressive_cube = ObjectHelper.get_cube(-1.5,0,0.05)
		self.on_ground_frame_counter = 0
		self.crawl_start_potential = None
		self.crawl_ignored_potential = 0.0
		self.initial_z = 0.8

	def alive_bonus(self, z, pitch):
		if self.frame%30==0 and self.frame>100 and self.on_ground_frame_counter==0:
			target_xyz  = np.array(self.body_xyz)
			robot_speed = np.array(self.robot_body.speed())
			angle = self.np_random.uniform(low=-3.14, high=3.14)
			from_dist   = 4.0
			attack_speed   = self.np_random.uniform(low=20.0, high=30.0)  # speed 20..30 (* mass in cube.urdf = impulse)
			time_to_travel = from_dist / attack_speed
			target_xyz += robot_speed*time_to_travel  # predict future position at the moment the cube hits the robot
			position = [target_xyz[0] + from_dist*np.cos(angle),
				target_xyz[1] + from_dist*np.sin(angle),
				target_xyz[2] + 1.0]
			attack_speed_vector = target_xyz - np.array(position)
			attack_speed_vector *= attack_speed / np.linalg.norm(attack_speed_vector)
			attack_speed_vector += self.np_random.uniform(low=-1.0, high=+1.0, size=(3,))
			self.aggressive_cube.reset_position(position)
			self.aggressive_cube.reset_velocity(linearVelocity=attack_speed_vector)
		if z < 0.8:
			self.on_ground_frame_counter += 1
		elif self.on_ground_frame_counter > 0:
			self.on_ground_frame_counter -= 1
		# End episode if the robot can't get up in 170 frames, to save computation and decorrelate observations.
		return self.potential_leak() if self.on_ground_frame_counter<170 else -1

	def potential_leak(self):
		z = self.body_xyz[2]		  # 0.00 .. 0.8 .. 1.05 normal walk, 1.2 when jumping
		z = np.clip(z, 0, 0.8)
		return z/0.8 + 1.0			# 1.00 .. 2.0

	def calc_potential(self):
		# We see alive bonus here as a leak from potential field. Value V(s) of a given state equals
		# potential, if it is topped up with gamma*potential every frame. Gamma is assumed 0.99.
		#
		# 2.0 alive bonus if z>0.8, potential is 200, leak gamma=0.99, (1-0.99)*200==2.0
		# 1.0 alive bonus on the ground z==0, potential is 100, leak (1-0.99)*100==1.0
		#
		# Why robot whould stand up: to receive 100 points in potential field difference.
		flag_running_progress = Humanoid.calc_potential(self)

		# This disables crawl.
		if self.body_xyz[2] < 0.8:
			if self.crawl_start_potential is None:
				self.crawl_start_potential = flag_running_progress - self.crawl_ignored_potential
				#print("CRAWL START %+0.1f %+0.1f" % (self.crawl_start_potential, flag_running_progress))
			self.crawl_ignored_potential = flag_running_progress - self.crawl_start_potential
			flag_running_progress  = self.crawl_start_potential
		else:
			#print("CRAWL STOP %+0.1f %+0.1f" % (self.crawl_ignored_potential, flag_running_progress))
			flag_running_progress -= self.crawl_ignored_potential
			self.crawl_start_potential = None

		return flag_running_progress + self.potential_leak()*100


class Atlas(WalkerBase, URDFBasedRobot):
	random_yaw = False
	foot_list = ["r_foot", "l_foot"]
	def __init__(self):
		WalkerBase.__init__(self, power=2.9)
		URDFBasedRobot.__init__(self, "atlas/atlas_description/atlas_v4_with_multisense.urdf", "pelvis", action_dim=30, obs_dim=70)

	def alive_bonus(self, z, pitch):
		# This is debug code to fix unwanted self-collisions:
		#for part in self.parts.values():
		#	contact_names = set(x.name for x in part.contact_list())
		#	if contact_names:
		#		print("CONTACT OF '%s' WITH '%s'" % (part.name, ",".join(contact_names)) )

		x,y,z = self.head.pose().xyz()
		# Failure mode: robot doesn't bend knees, tries to walk using hips.
		# We fix that by a bit of reward engineering.
		knees = np.array([j.current_relative_position() for j in [self.jdict["l_leg_kny"], self.jdict["r_leg_kny"]]], dtype=np.float32).flatten()
		knees_at_limit = np.count_nonzero(np.abs(knees[0::2]) > 0.99)
		return +4-knees_at_limit if z > 1.3 else -1

	def robot_specific_reset(self):
		WalkerBase.robot_specific_reset(self)
		self.set_initial_orientation(yaw_center=0, yaw_random_spread=np.pi)
		self.head = self.parts["head"]

	def set_initial_orientation(self, yaw_center, yaw_random_spread):
		if not self.random_yaw:
			yaw = yaw_center
		else:
			yaw = yaw_center + self.np_random.uniform(low=-yaw_random_spread, high=yaw_random_spread)

		position = [self.start_pos_x, self.start_pos_y, self.start_pos_z + 1.0]
		orientation = [0, 0, yaw]  # just face random direction, but stay straight otherwise
		self.robot_body.reset_pose(position, p.getQuaternionFromEuler(orientation))
		self.initial_z = 1.5