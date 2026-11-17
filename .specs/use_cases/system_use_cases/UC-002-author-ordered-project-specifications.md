# Use Case: Author Ordered Project Specifications

## Overview

**Use Case ID:** UC-002  
**Use Case Name:** Author Ordered Project Specifications  
**Primary Actor:** Specs orchestration skill  
**Goal:** The workflow creates and verifies the project specification artifacts in dependency order.  
**Trigger:** A project owner starts or updates a specification effort.  
**Status:** Draft

**Requirements:** [FR-001, FR-002, FR-003](../../reqs/requirements.db)

## Preconditions

- The workspace path is absolute and points to an existing project.
- Specialist authoring guidance is available for each requested artifact type.

## Main Success Scenario

1. The workflow inspects the project evidence and existing specification artifacts.
2. The workflow authors requirements and records them in the project registry.
3. The workflow queries the registry and confirms the requirements.
4. The workflow authors business use cases from the requirements.
5. The workflow authors an entity model from the requirements and business use cases.
6. The workflow authors system use cases from the requirements and entity model.
7. The workflow authors functional diagrams from the system use cases.
8. The workflow indexes existing artifact paths and verifies the specification set.

## Alternative Flows

### A1: A prerequisite stage is incomplete

**Trigger:** A required prior stage is missing or fails validation (step 1)  
**Flow:**

1. The workflow reports the missing input or failed validation.
2. The workflow does not create dependent artifacts.
3. Use case ends.

## Postconditions

### Success Postconditions

- Requirements are queryable from the project registry.
- Every indexed artifact exists under the project's `.specs` directory.
- Each artifact follows the declared dependency order.

### Failure Postconditions

- No dependent artifact is marked complete after a prerequisite failure.

## Business Rules

### BR-001: Artifact order

The workflow proceeds from requirements to business use cases, entity model, system use cases, and functional diagrams.

### BR-002: Workspace isolation

Project requirements and artifact metadata are stored only in that project's `.specs` registry.
