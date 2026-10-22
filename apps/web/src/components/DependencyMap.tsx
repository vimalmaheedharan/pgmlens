import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";
import { statusLabel } from "../lib/format";
import { layerLayout } from "../lib/layout";
import type { Issue, ProgramDetail } from "../types";

type IssueNodeData = { issue: Issue; selected: boolean };
type IssueNode = Node<IssueNodeData, "issue">;

function IssueNodeView({ data }: NodeProps<IssueNode>) {
  const { issue, selected } = data;
  const classes = ["inode", `s-${issue.status}`, issue.critical ? "critical" : "", issue.waiting ? "waiting" : "", selected ? "selected" : ""];
  return (
    <div className={classes.filter(Boolean).join(" ")}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="inode-top">
        <strong>{issue.key}</strong>
        <span className="small">{statusLabel[issue.status]}</span>
      </div>
      <div className="inode-title">{issue.title}</div>
      <div className="inode-owner small">{issue.assignee ?? "No owner"}</div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

const nodeTypes = { issue: IssueNodeView };
const MARKER = { type: MarkerType.ArrowClosed, color: "#6b7f86", width: 16, height: 16 };

type Scope = "focus" | "all";

export function DependencyMap({ detail }: { detail: ProgramDetail }) {
  const [scope, setScope] = useState<Scope>("focus");
  const [milestone, setMilestone] = useState<string>("");
  const [hideDone, setHideDone] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const byId = useMemo(() => new Map(detail.issues.map((i) => [i.id, i])), [detail.issues]);

  const { nodes, edges, hidden } = useMemo(() => {
    const all = new Set(detail.graph.nodes);
    let visible = new Set([...all].filter((id) => byId.has(id)));
    if (hideDone) visible = new Set([...visible].filter((id) => byId.get(id)!.status !== "done"));
    if (milestone) visible = new Set([...visible].filter((id) => byId.get(id)!.milestone_id === milestone));
    if (scope === "focus") {
      const core = new Set([...visible].filter((id) => byId.get(id)!.critical));
      const near = new Set(core);
      for (const e of detail.graph.edges) {
        if (core.has(e.source) && visible.has(e.target)) near.add(e.target);
        if (core.has(e.target) && visible.has(e.source)) near.add(e.source);
      }
      visible = near;
    }
    const keptEdges = detail.graph.edges.filter((e) => visible.has(e.source) && visible.has(e.target));
    const ids = [...visible];
    const placed = layerLayout(ids, keptEdges);
    const rfNodes: IssueNode[] = ids.map((id) => ({
      id,
      type: "issue",
      position: placed.get(id) ?? { x: 0, y: 0 },
      data: { issue: byId.get(id)!, selected: id === selectedId },
      draggable: true,
    }));
    const rfEdges: Edge[] = keptEdges.map((e) => ({
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      markerEnd: MARKER,
      className: `${e.critical ? "edge-critical" : "edge-plain"} ${e.unresolved ? "" : "edge-resolved"}`,
    }));
    return { nodes: rfNodes, edges: rfEdges, hidden: all.size - ids.length };
  }, [detail.graph, byId, hideDone, milestone, scope, selectedId]);

  const selected = selectedId ? byId.get(selectedId) : undefined;
  const chain = detail.graph.critical_path.map((id) => byId.get(id)).filter((i): i is Issue => Boolean(i));

  return (
    <div className="depmap">
      <div className="controls" role="group" aria-label="Map filters">
        <fieldset>
          <legend>Show</legend>
          <label>
            <input type="radio" name="scope" checked={scope === "focus"} onChange={() => setScope("focus")} />
            The critical path and what touches it
          </label>
          <label>
            <input type="radio" name="scope" checked={scope === "all"} onChange={() => setScope("all")} />
            Every dependency
          </label>
        </fieldset>
        <label className="field">
          Milestone
          <select value={milestone} onChange={(e) => setMilestone(e.target.value)}>
            <option value="">All milestones</option>
            {detail.milestones.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
          Hide finished work
        </label>
      </div>

      <div className="flow" role="img" aria-label={`Dependency map with ${nodes.length} issues. The same chain is listed in order below.`}>
        {nodes.length === 0 ? (
          <p className="empty">No open dependencies match these filters. Try showing every dependency.</p>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.2}
            nodesConnectable={false}
            colorMode="system"
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>

      <p className="muted small legend">
        Thick lines are the critical path: the longest chain of remaining work. A dashed outline means the issue is waiting on a blocker. Muted lines point from work that is already done.
        {hidden > 0 && ` ${hidden} more issues are hidden by the current filters.`}
      </p>

      {selected && (
        <div className="selection" aria-live="polite">
          <strong>{selected.key}</strong> {selected.title}. {statusLabel[selected.status]}, {selected.assignee ?? "no owner"}
          {selected.waiting ? ", waiting on a blocker" : ""}
          {selected.url && (
            <>
              {" "}
              <a href={selected.url} target="_blank" rel="noopener noreferrer">
                Open in tracker
              </a>
            </>
          )}
        </div>
      )}

      {chain.length > 0 && (
        <section className="chain">
          <h3>
            The longest chain of work, in order ({detail.analysis.graph.critical_path.length} points)
          </h3>
          <ol>
            {chain.map((issue) => (
              <li key={issue.id}>
                <strong>{issue.key}</strong> {issue.title}
                <span className="muted small">
                  {" "}
                  {statusLabel[issue.status]}, {issue.assignee ?? "no owner"}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
