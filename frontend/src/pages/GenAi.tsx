import { useQuery } from '@tanstack/react-query'

import ProjectCard from '@/components/genai/ProjectCard'
import EmptyState from '@/components/ui/EmptyState'
import ErrorPanel from '@/components/ui/ErrorPanel'
import Spinner from '@/components/ui/Spinner'
import { fetchClusterInfo, fetchGenAiProjects, fetchWorkloads } from '@/lib/api'
import { formatCpu, formatMemory } from '@/lib/format'
import type { GenAiProject, Workload } from '@/lib/schemas'

export default function GenAi() {
  const { data, error, isPending } = useQuery({
    queryKey: ['genai', 'projects'],
    queryFn: fetchGenAiProjects,
    refetchInterval: 10_000,
  })
  const workloads = useQuery({ queryKey: ['workloads'], queryFn: () => fetchWorkloads() })
  const info = useQuery({ queryKey: ['cluster', 'info'], queryFn: fetchClusterInfo })
  const readOnly = info.data?.safety.read_only ?? true

  if (isPending) return <Spinner label="Reading the namespace…" />
  if (error) return <ErrorPanel title="Could not list GenAI projects" error={error} />

  const byRef = new Map<string, Workload>(
    (workloads.data ?? []).map((w) => [`${w.kind}/${w.name}`, w]),
  )

  const paired = data.filter((p) => p.status === 'paired')
  const withoutRetriever = data.filter((p) => p.status === 'project_only')
  const withoutProject = data.filter((p) => p.status === 'retriever_only')
  const unidentified = data.filter((p) => p.status === 'unidentified')

  return (
    <div className="space-y-8">
      {data.length === 0 ? (
        <EmptyState
          title="No GenAI releases here."
          hint="An AutoGraph or GraphRAG retriever release would appear on this page, paired with the project it serves."
        />
      ) : (
        <p className="text-xs text-muted">
          {data.length} project{data.length === 1 ? '' : 's'} · {paired.length} with a retriever
          {withoutProject.length > 0 && (
            <span className="text-pit">
              {' '}
              · {reserved(withoutProject, 'cpu')} CPU and {reserved(withoutProject, 'memory')} held
              by retrievers with no project service
            </span>
          )}
        </p>
      )}

      <Section
        title="Projects with a retriever"
        hint="An AutoGraph release and a retriever naming the same project and database"
        projects={paired}
        workloads={byRef}
        readOnly={readOnly}
      />

      <Section
        title="Projects with no retriever"
        hint="Nothing is serving queries for these"
        projects={withoutRetriever}
        workloads={byRef}
        readOnly={readOnly}
      />

      <Section
        title="Retrievers with no project service"
        hint="Usually a leftover: the AutoGraph release is gone, the retriever still runs"
        projects={withoutProject}
        workloads={byRef}
        readOnly={readOnly}
      />

      <Section
        title="Project could not be read"
        hint="The project name arrives through a secret or field reference, which this tool does not resolve"
        projects={unidentified}
        workloads={byRef}
        readOnly={readOnly}
      />
    </div>
  )
}

function Section({
  title,
  hint,
  projects,
  workloads,
  readOnly,
}: {
  title: string
  hint: string
  projects: GenAiProject[]
  workloads: Map<string, Workload>
  readOnly: boolean
}) {
  // An empty section is noise: the other sections already say what is here.
  if (projects.length === 0) return null

  return (
    <section>
      <header className="mb-3 flex flex-wrap items-baseline gap-3">
        <h2 className="text-sm font-semibold text-body">{title}</h2>
        <p className="text-xs text-muted">
          {projects.length} · {hint}
        </p>
      </header>
      <div className="grid gap-3 xl:grid-cols-2">
        {projects.map((project) => (
          <ProjectCard
            key={project.key}
            project={project}
            workloads={workloads}
            readOnly={readOnly}
          />
        ))}
      </div>
    </section>
  )
}

/** What these releases reserve - not what is reclaimable, which needs usage. */
function reserved(projects: GenAiProject[], resource: 'cpu' | 'memory'): string {
  if (resource === 'cpu') {
    const cores = projects.reduce((sum, p) => sum + (p.resources.requests.cpu_cores ?? 0), 0)
    return formatCpu(cores)
  }
  const bytes = projects.reduce((sum, p) => sum + (p.resources.requests.memory_bytes ?? 0), 0)
  return formatMemory(bytes)
}
