import { AlertTriangle, Bot, Database, ExternalLink, Search } from 'lucide-react'
import { Link } from 'react-router-dom'

import ProtectedBadge from '@/components/actions/ProtectedBadge'
import WorkloadActions from '@/components/actions/WorkloadActions'
import DualBar from '@/components/resources/DualBar'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import { formatCpu, formatMemory } from '@/lib/format'
import type { GenAiComponent, GenAiProject, Workload } from '@/lib/schemas'
import { formatUptime } from '@/lib/uptime'

const STATUS: Record<GenAiProject['status'], { tone: 'good' | 'warn' | 'neutral'; label: string }> =
  {
    paired: { tone: 'good', label: 'paired' },
    project_only: { tone: 'warn', label: 'no retriever' },
    retriever_only: { tone: 'warn', label: 'no project service' },
    unidentified: { tone: 'neutral', label: 'project not identified' },
  }

const ROLE_LABEL: Record<GenAiComponent['role'], string> = {
  project: 'AutoGraph',
  retriever: 'Retriever',
  importer: 'Importer',
}

interface Props {
  project: GenAiProject
  /** Keyed "kind/name" - the actions need the real workload, not a copy of it. */
  workloads: Map<string, Workload>
  readOnly: boolean
}

export default function ProjectCard({ project, workloads, readOnly }: Props) {
  const status = STATUS[project.status]
  const components = [
    ...(project.project ? [project.project] : []),
    ...project.retrievers,
    ...project.others,
  ]

  return (
    <Card className="p-4">
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="min-w-0 text-sm font-semibold break-words text-body">
          {project.project_name ?? 'Project not identified'}
        </h3>
        {project.db_name && (
          <Badge tone="accent" mono title="The database this project reads and writes">
            <Database size={10} aria-hidden />
            {project.db_name}
          </Badge>
        )}
        <Badge tone={status.tone}>{status.label}</Badge>
        {project.warning_count > 0 && (
          <Badge tone="bad" title="Warning events across this project's releases">
            <AlertTriangle size={10} aria-hidden />
            {project.warning_count}
          </Badge>
        )}
      </header>

      {project.status === 'retriever_only' && (
        <p className="mt-2 text-[11px] text-muted">
          No AutoGraph release is running for this project, so nothing is importing into it. The
          retriever below still holds its reservation.
        </p>
      )}
      {project.status === 'project_only' && (
        <p className="mt-2 text-[11px] text-muted">
          No retriever is running for this project, so it cannot answer a query.
        </p>
      )}
      {project.status === 'unidentified' && (
        <p className="mt-2 text-[11px] text-muted">
          These releases name their project through a secret or field reference, which this tool
          does not resolve. They are listed rather than guessed at.
        </p>
      )}

      <div className="mt-3 space-y-2">
        {components.map((component) => (
          <ComponentRow
            key={`${component.kind}/${component.name}`}
            component={component}
            workload={workloads.get(`${component.kind}/${component.name}`)}
            readOnly={readOnly}
          />
        ))}
      </div>
    </Card>
  )
}

function ComponentRow({
  component,
  workload,
  readOnly,
}: {
  component: GenAiComponent
  workload: Workload | undefined
  readOnly: boolean
}) {
  const Icon = component.role === 'retriever' ? Search : Bot
  const name = component.name
  const models = [component.chat_model, component.embedding_model].filter(Boolean).join(' · ')

  return (
    <div className="rounded-md border border-line bg-cream p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-[11px] text-muted">
          <Icon size={12} aria-hidden />
          {ROLE_LABEL[component.role]}
        </span>
        {component.service ? (
          <Link
            to={`/services/${encodeURIComponent(component.service)}`}
            className="font-mono text-xs break-all text-arango hover:underline"
          >
            {name}
          </Link>
        ) : (
          <span className="font-mono text-xs break-all text-body">{name}</span>
        )}
        {workload?.desired_replicas === 0 && (
          <Badge tone="neutral" title="Scaled to 0 replicas on purpose">
            stopped
          </Badge>
        )}
        {workload && workload.desired_replicas > 0 && workload.ready_replicas === 0 && (
          <Badge
            tone="bad"
            title={`Wants ${workload.desired_replicas} replica(s); none are ready`}
          >
            not ready
          </Badge>
        )}
        {component.chart_version && (
          <Badge tone="neutral" mono>
            {component.chart_version}
          </Badge>
        )}
        <ProtectedBadge protection={component.protection} />
        {component.route_path && (
          <a
            href={component.route_path}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-mono text-[11px] text-arango hover:underline"
          >
            <ExternalLink size={10} aria-hidden />
            {component.route_path}
          </a>
        )}
        <span className="ml-auto">
          {workload && <WorkloadActions workload={workload} readOnly={readOnly} />}
        </span>
      </div>

      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <dl className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <dt className="text-muted">Pods</dt>
            <dd className="font-mono text-body">
              {component.ready_pods}/{component.pod_count}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Up</dt>
            <dd className="font-mono text-body">{formatUptime(component.age_seconds)}</dd>
          </div>
          <div>
            <dt className="text-muted">Restarts</dt>
            <dd className="font-mono text-body">{component.restart_count}</dd>
          </div>
        </dl>

        <div className="space-y-1.5">
          <DualBar
            label="CPU"
            value={component.resources.usage.cpu_cores}
            total={component.resources.requests.cpu_cores}
            format={formatCpu}
          />
          <DualBar
            label="Memory"
            value={component.resources.usage.memory_bytes}
            total={component.resources.requests.memory_bytes}
            format={formatMemory}
          />
        </div>
      </div>

      {models && <p className="mt-2 font-mono text-[11px] text-muted">{models}</p>}
    </div>
  )
}
