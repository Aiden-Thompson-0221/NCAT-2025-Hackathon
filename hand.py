#!/usr/bin/env python3
# /// script
# dependencies = ["matplotlib", "numpy"]
# ///

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

def rot_x(theta):
    c, s = np.cos(theta), np.sin(theta)
    T = np.eye(4)
    T[1,1]=c; T[1,2]=-s
    T[2,1]=s; T[2,2]=c
    return T

def rot_y(theta):
    c, s = np.cos(theta), np.sin(theta)
    T = np.eye(4)
    T[0,0]=c; T[0,2]=s
    T[2,0]=-s; T[2,2]=c
    return T

def rot_z(theta):
    c, s = np.cos(theta), np.sin(theta)
    T = np.eye(4)
    T[0,0]=c; T[0,1]=-s
    T[1,0]=s; T[1,1]=c
    return T

def translate(x,y,z):
    T = np.eye(4)
    T[:3,3] = [x,y,z]
    return T

class Finger:
    """
    Kinematic chain for one finger.
    For regular fingers: lengths = [proximal, middle, distal] (3 joints MCP,PIP,DIP)
    For thumb: lengths = [proximal, distal] with an extra opposition (CMC) joint.
    Segments extend along +Y after flexion rotations about local X.
    """
    def __init__(self, name, base_T, lengths, is_thumb=False, fan_angle=0.0):
        self.name = name
        self.base_T = base_T @ rot_z(fan_angle)
        self.lengths = lengths
        self.is_thumb = is_thumb

    def forward_kinematics(self, q, wrist_T=None):
        """
        q:
         thumb: [opposition(cmc_z), mcp_flex_x, ip_flex_x]
         finger: [mcp_flex_x, pip_flex_x, dip_flex_x]
        Returns list of 3D positions from wrist -> base -> joints ... -> tip.
        """
        if wrist_T is None:
            wrist_T = np.eye(4)

        # Start at wrist, then go to finger base
        T_wrist = wrist_T.copy()
        positions = [T_wrist[:3, 3].copy()]  # wrist point

        T = T_wrist @ self.base_T
        positions.append(T[:3, 3].copy())    # base point

        if self.is_thumb:
            cmc = q[0] if len(q)>0 else 0.0
            mcp = q[1] if len(q)>1 else 0.0
            ip  = q[2] if len(q)>2 else 0.0

            # Opposition about Z at the base (no translation)
            T = T @ rot_z(cmc)

            # MCP
            T = T @ rot_x(mcp) @ translate(0.0, self.lengths[0], 0.0)
            positions.append(T[:3,3].copy())

            # IP
            if len(self.lengths)>1:
                T = T @ rot_x(ip) @ translate(0.0, self.lengths[1], 0.0)
                positions.append(T[:3,3].copy())
        else:
            mcp = q[0] if len(q)>0 else 0.0
            pip = q[1] if len(q)>1 else 0.0
            dip = q[2] if len(q)>2 else 0.0

            # MCP
            T = T @ rot_x(mcp) @ translate(0.0, self.lengths[0], 0.0)
            positions.append(T[:3,3].copy())
            # PIP
            if len(self.lengths)>1:
                T = T @ rot_x(pip) @ translate(0.0, self.lengths[1], 0.0)
                positions.append(T[:3,3].copy())
            # DIP
            if len(self.lengths)>2:
                T = T @ rot_x(dip) @ translate(0.0, self.lengths[2], 0.0)
                positions.append(T[:3,3].copy())

        return positions

class HandSim:
    def __init__(self):
        # Segment lengths (cm) approximations
        self.lengths = {
            "thumb":  [3.0, 2.2],
            "index":  [4.5, 2.8, 2.0],
            "middle": [5.0, 3.0, 2.2],
            "ring":   [4.3, 2.6, 1.9],
            "pinky":  [3.2, 2.0, 1.6],
        }

        # Base positions (cm) relative to wrist origin (0,0,0)
        # Hand roughly lies in XY plane, Y forward, X lateral (thumb negative X)
        self.base_pos = {
            "thumb":  (-2.0, 1.6, -.2),  # adjusted: closer to center (less |x|), slightly forward & higher
            "index":  (-1.5, 4.2,  0.0),
            "middle": ( 0.0, 4.4,  0.2),
            "ring":   ( 1.5, 4.2,  0.0),
            "pinky":  ( 3.0, 3.7, -0.1),
        }

        # Fan angles (spread) in radians about Z
        self.fan = {
            "thumb":  np.deg2rad(-25),  # reduced spread so it starts more open, not crossing index
            "index":  np.deg2rad(10),
            "middle": 0.0,
            "ring":   np.deg2rad(-10),
            "pinky":  np.deg2rad(-20),
        }

        self.fingers_order = ["thumb","index","middle","ring","pinky"]
        self.fingers = []
        for name in self.fingers_order:
            base_T = np.eye(4)
            base_T[:3,3] = self.base_pos[name]
            is_thumb = (name=="thumb")
            finger = Finger(
                name=name,
                base_T=base_T,
                lengths=self.lengths[name],
                is_thumb=is_thumb,
                fan_angle=self.fan[name]
            )
            self.fingers.append(finger)

        # Max flex (radians) (approx)
        self.max_flex = {
            "thumb":  (np.deg2rad(55), np.deg2rad(70), np.deg2rad(65)),  # opposition, mcp, ip
            "index":  (np.deg2rad(85), np.deg2rad(105), np.deg2rad(80)),
            "middle": (np.deg2rad(90), np.deg2rad(110), np.deg2rad(85)),
            "ring":   (np.deg2rad(85), np.deg2rad(100), np.deg2rad(75)),
            "pinky":  (np.deg2rad(80), np.deg2rad(95),  np.deg2rad(70)),
        }

        self.fig = None
        self.ax = None
        self.lines = []
        self.palm_lines = []
        self.wrist_T = np.eye(4)  # allow moving wrist later if needed

    def setup_scene(self):
        self.fig = plt.figure(figsize=(11,8))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_xlim(-6,6)
        self.ax.set_ylim(-2,9)
        self.ax.set_zlim(-3,5)
        self.ax.set_xlabel("X (cm)")
        self.ax.set_ylabel("Y (cm)")
        self.ax.set_zlabel("Z (cm)")
        self.ax.set_title("Opposable Thumb Hand Fist Animation")

        # Draw wrist
        self.ax.scatter([0],[0],[0], c='k', s=80)

        # Palm perimeter (simple polygon)
        palm_pts = [
            (-3.5, 1.0, -0.2),
            (-3.5, 3.0, 0.0),
            ( 3.5, 3.0, 0.0),
            ( 3.5, 1.0, -0.2),
            (-3.5, 1.0, -0.2)
        ]
        px, py, pz = zip(*palm_pts)
        self.ax.plot(px, py, pz, 'k-', lw=2, alpha=0.6)

        # Finger base markers + lines placeholders
        colors = ["tab:red","tab:blue","tab:green","tab:orange","tab:purple"]
        for i,f in enumerate(self.fingers):
            self.ax.scatter([f.base_T[0,3]],[f.base_T[1,3]],[f.base_T[2,3]],
                            c=colors[i], s=40)
            line, = self.ax.plot([],[],[],'o-', lw=3, markersize=5, color=colors[i],
                                 label=f.name.capitalize())
            self.lines.append(line)

        self.ax.legend()

    def pose_for_phase(self, phase):
        """
        phase in [0,1]; 0=open, 1=closed fist.
        Use easing for natural curl.
        """
        ease = 1 - (1 - phase)**2  # quadratic ease-in
        all_q = []
        for f in self.fingers:
            mx = self.max_flex[f.name]
            if f.is_thumb:
                # Opposition increases strongly at start, then flex
                cmc = ease * mx[0]
                mcp = ease * mx[1]
                ip  = ease * mx[2]
                all_q.append([cmc, mcp, ip])
            else:
                mcp = ease * mx[0] * 0.75
                pip = ease * mx[1] * 1.00
                dip = ease * mx[2] * 0.85
                all_q.append([mcp, pip, dip])
        return all_q

    def draw_pose(self, joint_sets):
        for finger, q, line in zip(self.fingers, joint_sets, self.lines):
            pos = finger.forward_kinematics(q, wrist_T=self.wrist_T)
            xs, ys, zs = zip(*pos)
            line.set_data(xs, ys)
            line.set_3d_properties(zs)
        return self.lines

    def animate(self):
        frames = 140
        phases = 0.5 * (1 - np.cos(np.linspace(0, 2*np.pi, frames)))  # open->fist->open
        poses = [self.pose_for_phase(p) for p in phases]

        def update(i):
            return self.draw_pose(poses[i])

        # Initial open hand
        self.draw_pose(self.pose_for_phase(0.0))
        ani = animation.FuncAnimation(self.fig, update, frames=frames,
                                      interval=50, blit=False, repeat=True)
        plt.show()
        return ani

def main():
    sim = HandSim()
    sim.setup_scene()
    sim.animate()

if __name__ == "__main__":
    main()