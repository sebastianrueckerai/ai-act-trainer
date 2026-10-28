# Critic calibration cases

One file per question, a list of cases. Each case is a draft the critic must judge, with
the label a person gave it. `history` is the conversation before the student's message as
`[role, text]` pairs, `message` the message, `outcome` and `tries` what the grader would
have said, `met` the must points already met (1-based), `expect` ship or retry, `faults`
the faults a retry must name (one named is a hit). Cases follow the holiday-request
pattern applied to pool questions and come from real sessions. Never add a case only to
make a failing draft of the day pass.
