# Comparison and recommendation

The measured numbers for this run (models, tokens, milliseconds, scores, agreement with the
rule-based reference) are in `evidence/comparison_numbers.txt` and are reproduced in section 8
of the submission. Both targets used the same input (same sha256) and the same agent code.
"Cloud stand-in" means the larger installed model behind the simulated managed endpoint;
"on-prem" means the smaller installed model. Both really ran on local Ollama.

## Cost (illustrative shape, no prices claimed)

- Real AWS: Fargate vCPU and memory per task-second, ECR storage, VPC endpoints or NAT
  processing for private networking, CloudWatch ingestion, and managed-model charges per input
  and output token. Cost scales with volume, is near zero when idle, and needs no capital.
- On-prem: hardware bought up front (sunk cost), electricity, cooling, and staff time to patch
  and operate it. Marginal cost per case is close to zero, but capacity is fixed and idle
  hardware still costs money.
- Break-even depends on volume and utilisation; this lab does not measure it.

## Complexity

AWS adds IAM, networking and registry decisions (the bulk of this lab) but offloads the model's
operation. On-prem removes IAM and cloud networking but adds model hosting, weight and package
staging, capacity planning, patching, and an update process the client must audit.

## Output quality

Read from `evidence/comparison_numbers.txt`: whether each model's factor points match the
reference computed from the prompt's own rules, whether the final scores agree, and the token
and latency numbers. This is one input, one run per target at temperature 0 with a fixed seed.
It shows what happened on this input; it does not establish a general quality ranking. A
smaller model is more likely to misapply the arithmetic rules; the Week 8 code recomputes the
total but does not correct wrong per-factor points, so a wrong factor is a wrong score.

## Recommendation

- Client with strict data residency (regulated insurer, sovereignty rules, no third-party
  processing of applicant data): deploy on-prem with Ollama. Accept the smaller model and
  add a human-review rule for scores near decision thresholds, and pin the model digest in the
  release record. The residency guarantee is worth more than the quality gap.
- Client without residency constraints: deploy on AWS with the managed model, the dedicated
  role, private subnets with endpoints, and per-token pricing. Better model quality and no
  hardware to run; cost scales with use.
- Either way: keep the agent code identical and the model behind the `LLMClient` interface, so
  moving a client between targets is configuration, not a rewrite.
