# Graphs and subgraphs

One parent and three subgraphs composed into it as nodes:

| Graph | Kind | Why |
|---|---|---|
| `support` | parent | one message worked to an answer, for whoever is reading |
| `knowledge` | subgraph | it loops, and it is reached from more than one branch |
| `delivery` | subgraph | the only route to a customer, and the only irreversible step |
| `tool` | subgraph | propose a tool, clear it with a human, then run it |

It used to be two parents - `triage` for the customer and `chat` for the team -
which classified or routed, reached for the same knowledge base, and settled on
an answer, twice, in two files of the same length. They are one graph now, and
**the audience is a field on the context** rather than a second copy of the
graph. It decides three things: whether the ticket is graded, which capabilities
the decider is even offered, and whether the reply leaves through the delivery
gate instead of going straight back.

That last point is enforced by the output schema rather than by asking the model
nicely. Answering the customer there are no tools to reach for; answering the
team there is nobody to escalate to. A branch the model cannot name is one it
cannot take.

`GET /graphs/support.mermaid` renders the graph **from the compiled object**, so
the picture cannot disagree with the code. `xray=true` (the default) expands
the subgraphs inline; `xray=false` shows them as single boxes. The UI renders
these at `/graphs`.

Expanded, exactly as the compiled object emits it. Each subgraph carries its
own start and finish, which is what makes the early exits visible:

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	support_start(support_start)
	support_classify(support_classify)
	support_decide(support_decide)
	support_escalate(support_escalate)
	support_report_tool(support_report_tool)
	support_respond(support_respond)
	support_after_tool(support_after_tool)
	support_done(support_done)
	__end__([<p>__end__</p>]):::last
	__start__ --> support_start;
	delivery\3adelivery_done --> support_done;
	knowledge\3aknowledge_done --> support_respond;
	support_after_tool -.-> support_done;
	support_after_tool -.-> support_report_tool;
	support_after_tool -.-> support_respond;
	support_classify -.-> support_decide;
	support_decide -.-> knowledge\3a__start__;
	support_decide -.-> support_escalate;
	support_decide -.-> support_respond;
	support_decide -.-> tool\3atool_start;
	support_escalate -.-> delivery\3adelivery_start;
	support_report_tool -.-> support_respond;
	support_respond -.-> delivery\3adelivery_start;
	support_respond -.-> support_done;
	support_start -.-> delivery\3adelivery_start;
	support_start -.-> support_classify;
	support_start -.-> support_decide;
	support_start -.-> tool\3atool_start;
	tool\3atool_done --> support_after_tool;
	support_done --> __end__;
	subgraph knowledge
	knowledge\3a__start__(<p>__start__</p>)
	knowledge\3aknowledge_search(knowledge_search)
	knowledge\3aknowledge_refine(knowledge_refine)
	knowledge\3aknowledge_done(knowledge_done)
	knowledge\3a__start__ --> knowledge\3aknowledge_search;
	knowledge\3aknowledge_refine -.-> knowledge\3aknowledge_search;
	knowledge\3aknowledge_search -.-> knowledge\3aknowledge_done;
	knowledge\3aknowledge_search -.-> knowledge\3aknowledge_refine;
	end
	subgraph tool
	tool\3atool_start(tool_start)
	tool\3atool_plan(tool_plan)
	tool\3atool_gate(tool_gate)
	tool\3atool_execute(tool_execute)
	tool\3atool_done(tool_done)
	tool\3atool_execute --> tool\3atool_done;
	tool\3atool_gate -.-> tool\3atool_done;
	tool\3atool_plan -.-> tool\3atool_done;
	tool\3atool_plan -.-> tool\3atool_execute;
	tool\3atool_plan -.-> tool\3atool_gate;
	tool\3atool_start -.-> tool\3atool_done;
	tool\3atool_start -.-> tool\3atool_execute;
	tool\3atool_start -.-> tool\3atool_plan;
	end
	subgraph delivery
	delivery\3adelivery_start(delivery_start)
	delivery\3adelivery_screen(delivery_screen)
	delivery\3adelivery_approval(delivery_approval)
	delivery\3adelivery_send(delivery_send)
	delivery\3adelivery_done(delivery_done)
	delivery\3adelivery_approval -.-> delivery\3adelivery_done;
	delivery\3adelivery_screen -.-> delivery\3adelivery_approval;
	delivery\3adelivery_screen -.-> delivery\3adelivery_done;
	delivery\3adelivery_screen -.-> delivery\3adelivery_send;
	delivery\3adelivery_send --> delivery\3adelivery_done;
	delivery\3adelivery_start -.-> delivery\3adelivery_done;
	delivery\3adelivery_start -.-> delivery\3adelivery_screen;
	delivery\3adelivery_start -.-> delivery\3adelivery_send;
	end
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Where a run stops for a person is not on the picture, and that is the design
rather than an omission: a stop is a status the run ends with, not a place it
sits. `tool_gate` and `delivery_approval` put the proposal in front of somebody
and route to their graph's own exit, the same one a finished run leaves by.

Four things to read off it. `knowledge` loops, search to refine and back,
bounded by `KB_MAX_ATTEMPTS`. `tool` has its gate in the middle, so a proposal
reaches a person before anything runs. `delivery` is entered from three
different places in the parent, which is why the approval logic lives there
once rather than at each call site. And every graph has one entry and one
named finish, so an early exit lands on its own end rather than reaching past
it: `tool_plan` can stop without executing, `delivery_screen` without sending,
and the parent collects all of them at `support_done`.

## Human in the loop

Two things wait for a person, for different reasons.

A **drafted reply** stops at `delivery_approval` - but not every one, and that
is the point. Gating all of them meant the agent could never resolve a
ticket and the customer sat in front of an empty thread while the answer waited
on a screen they cannot see. `delivery.needs_a_person` decides: everything the
output screen finds is severe enough to stop a draft outright, so a finding
that survives to the gate is the *input* screen's - something in the ticket
addressed the model instead of describing a problem. That is worth a person
reading the reply, and it is rare. Every other draft is screened and sent.

The screen runs on all of them either way: `delivery` is still the only route
to `delivery_send`.

A **tool call** stops *before anything runs*. `tool_gate` puts the proposal on
the table, marks `tool_run` as pending and leaves by `tool_done`; the run ends
there, and the reviewer's answer arrives as a new one. The reviewer sees the
tool and the arguments the model chose, and can approve, **correct the
arguments**, or cancel - correcting £29 to £9 means £9 is what gets refunded.
Underneath, `@wrap_tool` refuses an approval-marked tool that arrives without
`approved=True`, so a mis-wired graph fails closed rather than spending money.

Approval is not the end of the risk. A process killed mid-refund leaves the
backend holding the state the run started from, so the redelivered decision
re-enters the graph, reaches that node again and refunds twice. A ledger keyed on
the run's own id and the tool claims the call before it is made and records the
result after, so the second attempt returns the first one's result while a
refund asked for later, in a new run, goes through. If the process dies between those two, nobody can know
whether the money moved, so the run says exactly that and asks a person to check
rather than guessing.

## Forms generated from a schema

One form engine, two sources of schema. The REST schemas are already Zod,
generated from the OpenAPI document. A tool's arguments arrive over the
WebSocket as JSON Schema, derived by the agent from the function's own
signature, and `lib/zodFromJsonSchema` converts them. `AutoForm` reads either
one for its fields, their types, which are required, their defaults and their
validation, so a form cannot ask for something the server or the tool will
reject.

That is what makes the tool gate work for a tool nobody wrote a form for: add a
tool to the agent and it is reviewable on its next proposal. The same engine
renders ticket creation and the model preferences at `/settings`, from
`TicketCreateRequest` and `ModelPreferenceRequest`.
