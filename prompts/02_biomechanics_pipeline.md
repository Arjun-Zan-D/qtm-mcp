# Biomechanical Pipeline Automation

**Use Case:** A biomechanics researcher wants to automate the processing of raw capture data through an Inverse Kinematics (IK) solver using OpenSim.

**Copy and paste the following prompt into your AI assistant:**

```text
I am working on the 'Athletics_Performance' QTM project. Please locate the raw marker trajectory data for trial 'Sprint_04' from today's session.

Here is what I need you to do:
1. Verify that the 3D marker coordinate data is present and there are no significant gaps in the markers attached to the lower limbs.
2. Trigger the OpenSim Inverse Kinematics pipeline for this trial using the configuration file 'Setup_IK_Sprint.xml' located in the project's OpenSim directory.
3. Once the pipeline finishes, parse the resulting `.mot` output file.
4. Extract the peak hip flexion and peak ankle dorsiflexion angles from the results.
5. Create a short markdown table summarizing these peak joint angles and tell me if they fall within the normal normative ranges for sprinting.
```
