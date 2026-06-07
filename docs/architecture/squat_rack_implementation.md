# Squat Rack Biomechanics System

**Lab-Grade Real-Time Coaching Architecture**

*Implementation & Technical Design Document | v1.0*

---

## Executive Summary

*A home squat rack with 4 integrated cameras, IR illumination, and a validated biomechanics pipeline delivering real-time coaching feedback at lab-grade accuracy. The system uses RTMPose for 2D keypoint detection, stereo triangulation for 3D reconstruction, OpenSim with a subject-scaled Rajagopal musculoskeletal model for inverse kinematics, and a layered ML fault detection system trained on synthetic OpenSim data and refined by real-world usage.*

---

## 1. Why This Architecture

The core insight driving every design decision: by integrating cameras directly into the squat rack, we solve the hardest problems in markerless biomechanics by design rather than by software.

An uncontrolled environment — a camera pointed at someone in a gym — requires solving occlusion, lighting variation, camera drift, and undefined capture volumes in software. These are extremely difficult, expensive, and ultimately limit accuracy. The integrated rack eliminates all of them at the hardware level.

### 1.1 What Integration Gives Us

- Camera positions are fixed and known at manufacturing time — factory calibration parameters ship with firmware, no user calibration required
- The capture volume is completely defined — roughly 1m × 1m × 2.2m — the entire pipeline can be optimized for this specific space
- Lighting is fully controllable via integrated IR illumination — performance is identical at 5am in a dark garage and noon in a bright gym
- Hardware sync is achievable cheaply — a single GPIO trigger line to all cameras from a sync controller
- We own the full stack — camera spec, lens, sync, mounting rigidity — no external variables

### 1.2 The Lab-Grade Claim

> **CRITICAL:** Lab-grade is a claim about validated accuracy, not about hardware cost. The claim requires concurrent validity data against a reference motion capture system (Vicon/Qualisys), with published RMSE < 5 degrees on joint angles. This validation must be done on the actual product hardware in product conditions — not on lab cameras.

The integrated rack, with controlled illumination, is operating in near-lab conditions. This closes most of the gap between a $200 integrated camera and a $2,000 industrial camera for this specific application.

---

## 2. Hardware Architecture

### 2.1 Camera Count Decision

Camera count is the most important hardware decision for a squat rack application. The analysis:

| Config | Advantages | Limitations |
|--------|-----------|-------------|
| **2 cameras** | Lowest cost, simple sync | One side always partially occluded. Bilateral symmetry analysis unreliable. Not recommended. |
| **4 cameras** | Full 360° coverage. Bilateral redundancy. All joints visible from 2+ cameras at all times. Handles occlusion robustly. | Higher BOM cost. More complex sync and calibration. |
| **6 cameras** | Covers walkout and re-rack phases. Full redundancy. | Significantly higher cost and processing load. Premium SKU territory. |

**Recommendation: Design for 4 cameras, launch with 4, offer 6 as a premium SKU.**

### 2.2 Camera Positioning

For a squat rack with 4 cameras, optimal positioning is two front-angled cameras and two rear-angled cameras at approximately 45-degree offset positions. This provides:

- Every major joint visible from at least 2 cameras simultaneously throughout the entire squat
- Robust bilateral keypoint coverage — both knees, both hips, both ankles always trackable
- Sufficient stereo baseline for accurate depth reconstruction
- Minimal dead zones in the capture volume

### 2.3 Camera Specification

Camera selection criteria in priority order:

- **Global shutter** — mandatory. Rolling shutter cameras produce motion blur artifacts during dynamic lifting that directly corrupt keypoint positions. This is non-negotiable.
- **Hardware sync capable** — cameras must accept an external trigger signal to ensure frame-perfect synchronization. Even 1-2 frame desync at 60fps introduces triangulation error during fast movements.
- **60fps minimum at 1080p** — temporal resolution matters more than spatial resolution for movement analysis. 1080p at 60fps outperforms 4K at 30fps for this application.
- **IR sensitivity** — cameras should operate effectively with near-IR illumination to enable lighting-invariant capture.

Target camera options:

- **Luxonis OAK-D series** ($150–250/unit at volume) — purpose-built for computer vision, global shutter, hardware sync, onboard neural network inference capable of running RTMPose on-device. Strong first choice.
- **FLIR Blackfly S USB3** ($500–800/unit) — industrial reliability, excellent driver support for multi-camera synchronized capture. Higher cost but established in research deployments.

### 2.4 Illumination

Integrate near-IR LED arrays into the rack uprights. Use cameras with IR-pass filters. This is a significant product quality differentiator and is how serious motion capture systems achieve lighting invariance. The performance difference between controlled IR illumination and ambient lighting on keypoint detection reliability is substantial — this should be treated as a core feature, not an accessory.

### 2.5 On-Device Compute

Processing architecture is a key product decision with significant implications for latency, cost, and user experience:

- **On-device** (Jetson Orin NX, ~$500 at volume): Full processing in the rack. Works without internet. No network latency. Harder to iterate post-launch. Required for real-time audio cues within the 200–300ms feedback latency budget.
- **Hybrid**: Pose estimation and fault detection on-device for real-time feedback. Historical analysis, model updates, and session reports via cloud. This is the recommended architecture — it meets the latency requirement for real-time coaching while enabling continuous model improvement.

### 2.6 Factory Calibration

Because camera positions are fixed by the rack geometry, stereo calibration parameters can be determined at manufacturing time using a volumetric calibration object (wand calibration preferred over checkerboard for this application). Parameters are stored in firmware and shipped with the unit.

In the field, a quick per-session verification runs automatically: user stands in the rack for 3 seconds at session start, system confirms cameras are undisturbed and updates the subject model if needed. No user-facing calibration complexity.

---

## 3. Software Pipeline

The pipeline is structured as independent, validatable layers. This is critical — when something breaks in production, you can isolate which layer failed. A black-box end-to-end model gives you none of that debuggability.

### 3.1 Full Pipeline Architecture

```
4 Cameras (hardware synced, 1080p @ 60fps)
    ↓
Layer 1: 2D Pose Estimation — RTMPose (fine-tuned)          ~5ms
    ↓
Layer 2: 3D Triangulation — Stereo geometry (math)           ~2ms
    ↓
Layer 3: Inverse Kinematics — OpenSim + Rajagopal model      ~15ms
    ↓
Layer 4: Fault Detection — Rules + ML models                 ~5ms
    ↓
Layer 5: Coaching Output — Audio cues + LLM language          ~3ms
    ↓
Total: ~30ms per frame → ~30fps real-time pipeline
```

### 3.2 Layer 1: 2D Pose Estimation

RTMPose is the correct choice. It is used in academic research, runs in real time on embedded hardware, and handles the COCO 17-keypoint skeleton required for downstream IK. Do not train this from scratch — the required dataset is in the millions of images.

What we do build: fine-tuning on our specific domain. Our cameras, our angles, our IR lighting, lifters under load with a barbell. Approximately 5,000–10,000 labeled frames from product cameras enables meaningful fine-tuning. A semi-automated labeling pipeline using lab ground truth sessions dramatically reduces cost.

> **KEY POINT:** ML models must never see raw video. After Layer 1, everything downstream operates on structured numerical data — joint coordinates and angles. This is the architectural decision that makes the rest of the system tractable.

### 3.3 Layer 2: 3D Triangulation

Stereo triangulation from calibrated cameras is a solved geometric problem. Use OpenCV's triangulation with factory calibration parameters. Do not use ML-based depth estimation — it introduces unnecessary error when proper stereo geometry is available.

With 4 cameras and known geometry, 3D reconstruction is robust to single-camera keypoint dropout. If one camera loses a joint due to occlusion, the remaining three cameras maintain triangulation quality. This is the primary reason 4 cameras is the minimum viable configuration.

### 3.4 Layer 3: Inverse Kinematics — The Most Critical Layer

This is where the existing prototype needs the most significant work. The analytical geometric solver must be replaced with proper OpenSim IK. Everything downstream — joint angles, fault detection, coaching feedback — is only as good as this layer.

#### 3.4.1 What OpenSim Is

OpenSim is the standard biomechanics simulation platform developed at Stanford, used in academic labs worldwide for 20+ years. It takes 3D keypoint positions as input and outputs joint angles, joint moments, and muscle forces with validated physics-based accuracy.

#### 3.4.2 The Rajagopal 2016 Model

The musculoskeletal model defines the digital skeleton — bones, joint constraints, degrees of freedom, muscle attachments. The Rajagopal 2016 full-body model is the most widely validated model currently available. It defines 37 degrees of freedom and 80 muscles based on cadaver data, and has been validated against experimental data across movement tasks including squatting. Using a published, peer-reviewed model means inheriting thousands of hours of existing validation work.

#### 3.4.3 Subject Scaling — Why It Is Non-Negotiable

The Rajagopal model defaults to approximately a 170cm, 75kg male reference subject. Running a 150cm female lifter through an unscaled model produces systematically wrong joint angles — errors of 5–15 degrees — for anyone who deviates from the reference anthropometry. This is most people.

Subject scaling adjusts every segment length and mass to match a specific person's body dimensions. It happens once at onboarding:

- User stands in a neutral position in front of the rack for 10 seconds
- 4-camera system captures 3D keypoint positions in this known pose
- OpenSim scaling tool compares observed inter-keypoint distances to model defaults
- Scale factors computed per segment — shoulder-to-elbow, elbow-to-wrist, hip-to-knee, knee-to-ankle
- Scaled model saved to user profile, used for all subsequent sessions

Without subject scaling, the system cannot claim lab-grade accuracy for anyone outside a narrow anthropometric band. This is a launch-blocking requirement, not a nice-to-have.

### 3.5 Layer 4: Fault Detection

Not all form faults are the same type of problem. Misclassifying fault type leads to building ML models for problems that need rules, and rules for problems that need ML.

| Fault | Type | Approach | Notes |
|-------|------|----------|-------|
| Depth achievement | **Type 1: Geometric** | Rule on IK output | Hip joint center below knee joint center. Simple, reliable, high value. |
| Bilateral asymmetry | **Type 1: Geometric** | Rule on IK output | Left vs right joint angle comparison throughout rep. Direct math once bilateral IK is accurate. |
| Heel rise | **Type 1: Geometric** | Rule on 3D output | Ankle joint vertical position change during descent. |
| Forward lean | **Type 1 + Anthro** | Rule + subject model | Trunk angle is a rule but acceptable threshold is body-type dependent. Subject scaling handles most of this. |
| Knee valgus | **Type 2: Dynamic** | ML: TCN model | Trajectory pattern, not single frame. Highest-value ML target. TCN on knee abduction angle time series. |
| Back rounding | **Type 2/3: Dynamic** | ML: TCN model (v2) | Harder labeling problem. v1: simple trunk angle rule. Upgrade to ML once 500+ labeled trials available. |

#### 3.5.1 ML Model Architecture: Temporal Convolutional Network (TCN)

For dynamic fault patterns (knee valgus, back rounding), a Temporal Convolutional Network operating on joint angle time series is the correct architecture. Key design decisions:

- **Input:** Rolling window of last 60–90 frames of joint angle data from IK output — not raw video, not raw keypoints
- **Architecture:** 3-layer TCN, 64 hidden units. Tiny, fast, runs easily on embedded hardware
- **Output:** Continuous severity score (0–3) rather than binary classification — enables proportional feedback
- **Training data:** Biomechanist-labeled squat trials, not model outputs or heuristics

#### 3.5.2 Rep Detection

The system needs to know when a rep starts and ends to organize analysis correctly. Peak detection on the hip flexion angle time series: when hip flexion exceeds a threshold (approximately 30 degrees) a rep is in progress; when it returns below that threshold the rep is complete and analysis is finalized for that rep. Simple, robust, implemented as a signal processing rule — no ML required.

### 3.6 Layer 5: Coaching Output

Two distinct output channels with different latency requirements:

- **Real-time audio cues during the set** — fires within 200–300ms of fault onset. Examples: "knees out" spoken immediately when valgus detected. This is the highest-value feedback channel because it is actionable while the movement is happening. This is why the end-to-end latency budget matters.
- **Between-set analysis dashboard** — rep-by-rep breakdown of depth, symmetry, faults detected with frame reference. Richer analysis that does not need to be real-time.
- **Post-session report** — trends across sets, comparison to previous sessions, specific recommendations. This is where the LLM coaching layer earns its place.

#### 3.6.1 LLM Integration

A large language model (Claude or equivalent) is appropriate for generating coaching feedback language — but only as a communication layer, not a decision-making layer. The LLM receives structured fault data from the validated pipeline and translates it into natural language coaching cues appropriate for the user's experience level and session history.

> **IMPORTANT:** The LLM is never making biomechanical decisions. It is only communicating decisions already made by the validated pipeline. This constraint must be enforced architecturally, not by prompt alone.

---

## 4. ML Training Strategy

### 4.1 Synthetic Data: The Strategic Advantage

OpenSim enables generation of synthetic training data at scale with perfect labels. This is one of the most powerful aspects of the architecture and fundamentally changes the training timeline.

**What Can Be Controlled in Synthetic Generation:**

- Body dimensions spanning the full population distribution — height, weight, segment lengths
- Movement parameters — squat depth, descent speed, stance width, toe angle
- Fault parameters — introduce knee valgus of exactly 8 degrees, lumbar flexion at a specific descent point, asymmetry of exactly 12 degrees left-to-right
- Dataset balance — 3,000 mild valgus cases, 3,000 severe, 4,000 no fault. Perfect balance by construction.

**Comparison with real-world data collection:**

| Real-World Collection | Synthetic OpenSim Generation |
|---|---|
| Hundreds of real subjects required | Parameterized body models cover full population |
| Biomechanist labels every trial manually | Labels are exact — defined when generating the fault |
| Months of data collection | Weeks of compute time |
| Severe faults rare in real populations — imbalanced datasets | Any fault severity at any prevalence on demand |
| Ethics approval for human subjects research required | No ethics approval required |

### 4.2 The Sim-to-Real Gap

Synthetic data alone is not sufficient. There is always a gap between idealized physics simulation and real human movement — noise, compensatory patterns, fatigue effects, clothing effects on keypoint detection. The correct approach:

```
Synthetic OpenSim data
    ↓
Train initial models (fast, cheap, controlled) → Working v1
    ↓
Deploy on real users → collect real joint angle data
    ↓
Fine-tune models on real data → Close sim-to-real gap
    ↓
Continuous improvement with data flywheel
```

Synthetic data bootstraps to a working v1 far faster than real data collection alone. Real data then continuously closes the gap. This is standard practice in robotics and computer vision.

### 4.3 The Data Flywheel

The integrated rack's most significant long-term asset is the data it generates. Every session from a consenting real user produces real joint angle time series data from real human movement. This data:

- Fine-tunes fault detection models beyond synthetic performance
- Calibrates rule-based thresholds across genuine population variance in body type and mobility
- Builds a longitudinal dataset of home squat biomechanics that does not exist anywhere else
- Compounds in value with every user and every session

> **STRATEGIC NOTE:** The data pipeline and user consent framework are as important as the ML models. Build this infrastructure from day one. The rack is not just a product — it is a data collection platform that improves over time.

### 4.4 Training Data Requirements by Component

| Component | Data Source | Quantity | Timeline |
|-----------|------------|----------|----------|
| RTMPose fine-tuning | Product cameras, semi-auto labeled | 5,000–10,000 frames | Before launch |
| Knee valgus TCN | Synthetic + biomechanist-labeled real trials | 500–1,000 trials | v2, 6–12 months post-launch |
| Back rounding TCN | Synthetic + labeled real trials | 1,000+ trials | v3, 12–18 months post-launch |
| Threshold calibration | Real users via data flywheel | 100–200 subjects | Ongoing post-launch |

### 4.5 Labeling Protocol

Before a single rack ships, a biomechanist-designed labeling tool and protocol must exist. Requirements:

- Video review interface with frame scrubbing and playback controls
- Severity rating scale (0–3) for each fault type — not binary good/bad
- Rating scale defined precisely enough that two different raters agree most of the time
- Inter-rater reliability measured before any labeled data is used for training

The labeling protocol is the most important thing the biomechanist can be building right now, ahead of any software development. Unreliable labels produce unreliable models regardless of pipeline quality.

---

## 5. Validation Requirements

Validation is not optional for a lab-grade claim. It must be done before that claim is made to any customer. The validation study design should be the biomechanist's primary focus in the near term.

### 5.1 Concurrent Validity Study

Bring the integrated rack system into a university biomechanics lab and run concurrent trials with their reference motion capture system (Vicon or Qualisys). Recommended protocol:

- 15–20 subjects across a range of body types, experience levels, and mobility profiles
- Each subject performs 5–10 squat trials at varying loads
- Simultaneous capture with both systems
- Primary metric: RMSE on joint angles (hip, knee, ankle) — target < 5 degrees
- Secondary metrics: bilateral symmetry agreement, depth detection accuracy, temporal consistency

This study can be structured as a research collaboration with a university biomechanics department. Offering co-authorship on any resulting publication typically enables lab access at low or no cost. The biomechanist's academic connections are the critical enabler here.

### 5.2 What Must Be Validated on Product Hardware

> **CRITICAL:** Validation data must come from the actual product cameras in product conditions — not from lab cameras. RMSE numbers measured on lab hardware tell you nothing defensible about consumer camera performance. The integrated rack with IR illumination is the product configuration that must be tested.

### 5.3 Test-Retest Reliability

Same subject, same lift, different sessions with re-calibration between sessions. The system must produce consistent joint angles across days. This validates that factory calibration holds over time and that subject scaling is stable.

### 5.4 What Accuracy Claims Can Be Made

After validation, accuracy claims must be tied specifically to what was validated:

- **Validated:** joint angles (hip, knee, ankle) during barbell back squat, RMSE against Vicon, specific subject population and load ranges
- **Not validated until tested:** other movements, other joint angles, force estimates, muscle activation estimates

Do not extend accuracy claims beyond what was measured. This is both an honesty requirement and a liability issue.

---

## 6. Real-Time Visualization

The visualization layer is what users interact with directly, but it should be built last — after the biomechanics pipeline is validated. Showing users a confidently wrong skeleton is worse than showing nothing.

### 6.1 Display Architecture Recommendation

| Option | Description | Complexity | Launch |
|--------|------------|------------|--------|
| **Multi-view 2D** | Simultaneous 2D views from multiple angles with skeleton overlay. How coaches naturally think about movement. | Low | **v1** |
| **3D Skeleton** | Stick figure or articulated skeleton rendered in 3D space from reconstructed joint positions. Simple to render from existing 3D coordinates. | Medium | **v2** |
| **3D Avatar** | Skinned 3D human model mirroring user movements in real time. Highest consumer engagement but significant engineering cost. | High | **v3** |

### 6.2 Latency Budget

For real-time audio coaching feedback to be effective, it must fire within 200–300ms of fault onset. The full chain:

| Stage | Latency | Notes |
|-------|---------|-------|
| Camera capture + transfer | ~16ms | At 60fps |
| RTMPose (4 views) | ~20ms | Jetson Orin NX |
| 3D Triangulation | ~2ms | Pure math |
| OpenSim IK | ~15–20ms | Benchmark early |
| Fault detection | ~5ms | TCN + rules |
| Audio output | ~10ms | |
| **TOTAL** | **~68–73ms** | **Well within 200ms budget** |

---

## 7. Development Roadmap

### Month 1–2: Foundation

- **Software engineer:** Set up OpenSim pipeline with Rajagopal model. Get subject scaling working on a static standing trial. Benchmark IK latency on target compute hardware.
- **Biomechanist:** Contact 2–3 university biomechanics labs about validation collaboration. Design fault labeling protocol and rating scales. Begin defining feedback rules for rule-based fault detectors.
- **Hardware engineer:** Resolve camera sync architecture. Build prototype 4-camera mount. Specify IR illumination system.

### Month 3–4: Integration

- Full pipeline running end-to-end on a single movement (squat). Recorded video input before real-time.
- Rule-based fault detectors operational: depth, symmetry, heel rise, forward lean.
- RTMPose fine-tuning on product camera footage begins.
- Labeling tool built and inter-rater reliability measured.

### Month 5–6: Validation

- Bring prototype rack into university lab. Run concurrent validity study against reference system.
- Measure RMSE on joint angles. Identify error sources and address highest-impact issues.
- Establish validated accuracy claims with specific numbers.

### Month 7–9: Real-Time and UX

- Full real-time pipeline at target framerate on target compute hardware.
- Real-time audio feedback implemented and tested.
- Multi-view 2D visualization with skeleton overlay.
- Between-set analysis dashboard.

### Month 10–12: ML Layer and Data Infrastructure

- Synthetic OpenSim data generation pipeline operational.
- Knee valgus TCN trained on synthetic data, integrated into pipeline.
- Data flywheel infrastructure — consent framework, data collection, storage, labeling queue.
- LLM coaching language layer integrated.

### Post-Launch: Continuous Improvement

- Real user data begins flowing into labeling queue.
- Fault detection models fine-tuned on real data quarterly.
- Back rounding model development as labeled dataset reaches threshold.
- Threshold calibration updated as population variance data accumulates.

---

## 8. Team Responsibilities

Each team member owns a distinct layer of the architecture. Clear ownership prevents duplication and ensures the critical path is covered.

| Role | Primary Responsibilities | Critical Path Items |
|------|------------------------|-------------------|
| **Biomechanist** | Musculoskeletal model selection and validation. Fault definition and labeling protocol. Validation study design. Feedback rule clinical grounding. | OpenSim/Rajagopal implementation. Labeling protocol with inter-rater reliability. University lab partnership for validation. |
| **Software Engineer** | Full pipeline implementation. RTMPose integration and fine-tuning. Triangulation and IK pipeline. Fault detection models. Real-time system optimization. | OpenSim IK latency on target hardware. TCN training pipeline. Data flywheel infrastructure. |
| **Hardware Engineer** | Camera selection and sync architecture. IR illumination design. Compute module integration. Factory calibration workflow. Mechanical mount design. | Hardware sync solution. IR illumination specification. Jetson Orin NX integration. GPIO trigger architecture. |
| **Founder** | Product vision and roadmap. University lab partnership development. User consent and data framework. Go-to-market strategy. Investor narrative. | Lab partnership outreach. Consent framework legal review. Pricing and BOM targets. |

---

## 9. Explicitly Out of Scope for V1

These are items that could consume significant time and must be deferred. Shipping a validated, accurate v1 with limited scope is more valuable than shipping a broad, unvalidated system.

- Muscle force or joint moment estimates presented to users — validation burden and liability is too high. Defer to v3 at earliest.
- Upper body movement analysis — focus squat first, validate completely, then expand
- Multiple movement types — squat only for v1. Deadlift, hinge, and press have different error profiles and require separate validation.
- 3D avatar visualization — high engineering cost for marginal accuracy benefit. Multi-view 2D is more useful for coaching.
- Force plate integration — valuable for research, not needed for coaching feedback
- EMG validation — the gold standard for muscle activation but requires hardware and protocol that is out of scope for v1
- Monocular depth estimation — unnecessary with proper stereo geometry. Adds complexity and reduces accuracy.
- Black-box end-to-end form classifier — untraceable, unvalidatable, and legally indefensible for health claims

---

## 10. Key Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| OpenSim IK too slow for real-time | **High** | Benchmark early on Jetson Orin NX. If too slow, train a lightweight neural network to approximate OpenSim output (model distillation). Build this contingency into schedule. |
| Validation RMSE > 5 degrees | **High** | Identify error source (IK, triangulation, or keypoint detection) using layered validation. Most likely source is IK or subject scaling — fix those first. |
| Camera sync drift in field | **High** | Hardware GPIO sync, not software sync. Per-session calibration verification detects drift. Fixed mounting prevents camera movement. |
| BOM too high for target price | **Medium** | Camera count, compute module, and IR illumination are the primary cost drivers. Design for 4 cameras but prototype with fewer to validate pipeline before committing to BOM. |
| Insufficient labeled data for ML models | **Medium** | Synthetic OpenSim data bootstraps v1. Rule-based fault detectors require no labeled data. ML models are v2 features gated on labeled dataset size. |
| Labeling inter-rater reliability too low | **Medium** | Invest in protocol design before labeling begins. Measure reliability before using any labeled data. Refine rating scale until reliability meets threshold. |

---

*Document Version 1.0 | Confidential*

*Prepared for internal team and technical review*
