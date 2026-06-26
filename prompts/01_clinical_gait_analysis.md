# Clinical Gait Analysis & EHR Reporting

**Use Case:** A clinician wants to compare a patient's pre-operative and post-operative gait metrics and generate a summary for the electronic health record (EHR).

**Copy and paste the following prompt into your AI assistant:**

```text
Please load the QTM project 'Xavier_Gait_Lab' and locate the session data for Patient ID 'PAT-8892'. 

I need you to:
1. Load the pre-operative capture session from '2023-05-12' and the post-operative session from '2024-01-10'.
2. Extract the clinical reports for both sessions, focusing specifically on spatio-temporal parameters (walking speed, cadence, stride length) and maximum knee flexion during the swing phase.
3. Compare the two sessions and calculate the percentage improvement in walking speed and knee flexion.
4. Draft a concise, professional clinical note summarizing these improvements. 
5. Finally, use the clinical output tool to push this drafted note to our authorized FHIR EHR endpoint.
```
