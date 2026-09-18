import { useEffect, type MouseEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import Card from '@/components/ui/Card'

const SECTIONS = [
  { id: 'start', title: 'Start here' },
  { id: 'capacity', title: 'Reading the numbers' },
  { id: 'reclaim', title: 'Free up unused capacity' },
  { id: 'actions', title: 'Scale, stop, kill, restart' },
  { id: 'pods', title: 'Kill a pod' },
  { id: 'restore', title: 'Restore a stopped service' },
  { id: 'database', title: 'Resize the database' },
  { id: 'genai', title: 'GenAI projects' },
  { id: 'missing', title: 'When a button is missing' },
  { id: 'safety', title: 'Safety settings' },
  { id: 'pages', title: 'The pages' },
] as const

export default function HowTo() {
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.replace(/^#/, ''))
    if (!id) return
    document.getElementById(id)?.scrollIntoView({ block: 'start' })
  }, [])

  return (
    <div className="mx-auto flex max-w-5xl gap-10">
      <nav aria-label="On this page" className="hidden w-44 shrink-0 lg:block">
        <p className="mb-2 text-[11px] font-medium tracking-wide text-muted uppercase">
          On this page
        </p>
        <ol className="sticky top-0 space-y-1.5">
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <TocLink id={section.id}>{section.title}</TocLink>
            </li>
          ))}
        </ol>
      </nav>

      <div className="min-w-0 max-w-3xl flex-1 space-y-5">
        <header>
          <h2 className="text-base font-semibold text-body">How to use this tool</h2>
          <p className="mt-1 max-w-prose text-xs text-muted">
            A short guide to reading the numbers and changing what is running in this namespace.
          </p>
        </header>

        <nav aria-label="On this page" className="lg:hidden">
          <Card className="p-3">
            <p className="mb-2 text-[11px] font-medium tracking-wide text-muted uppercase">
              On this page
            </p>
            <ol className="flex flex-wrap gap-x-3 gap-y-1">
              {SECTIONS.map((section) => (
                <li key={section.id}>
                  <TocLink id={section.id}>{section.title}</TocLink>
                </li>
              ))}
            </ol>
          </Card>
        </nav>

        <Section id="start" title="Start here">
          <p>
            Open <Page to="/">Overview</Page> for the big picture, then{' '}
            <Page to="/capacity">Capacity</Page> to see which workloads are holding more than they
            use. When you want to change something, open its{' '}
            <Page to="/services">service</Page> and use the buttons beside each workload.
          </p>
          <p>
            Look for a <span className="font-medium">read-only</span> chip in the top bar. While it
            is there, the buttons still appear but nothing will run.
          </p>
        </Section>

        <Section id="capacity" title="Reading the numbers">
          <p>Four figures show up on most pages:</p>
          <dl className="mt-3 space-y-2">
            <Term name="Used">
              Live CPU and memory. If the top bar shows{' '}
              <span className="font-medium">no metrics</span>, this figure is unavailable.
            </Term>
            <Term name="Reserved">
              What the pods asked Kubernetes to hold for them. The namespace pays for this whether
              the workload uses it or not.
            </Term>
            <Term name="Limit">
              The most a container is allowed to use. A container with no limit can take a whole
              node.
            </Term>
            <Term name="Budget">
              What reserved is measured against. <Page to="/settings">Settings</Page> shows where
              the figure comes from.
            </Term>
          </dl>
          <p>
            <span className="font-medium">Efficiency</span> is used divided by reserved.{' '}
            <span className="font-medium">Reclaimable</span> is the reserved capacity a workload is
            sitting on without using.
          </p>
        </Section>

        <Section id="reclaim" title="Free up unused capacity">
          <ol className="list-decimal space-y-2 pl-4">
            <li>
              <Page to="/">Overview</Page> shows how much is reclaimable across the namespace, with
              the biggest offenders listed underneath.
            </li>
            <li>
              <Page to="/capacity">Capacity</Page> ranks every over-reserved workload and lists
              pods running with no limit set.
            </li>
            <li>
              Click through to the service, then scale the workload down or stop it.
            </li>
          </ol>
          <p>
            Database members are handled separately. Resize those on the{' '}
            <Page to="/database">Database</Page> page.
          </p>
        </Section>

        <Section id="actions" title="Scale, stop, kill, restart">
          <p>
            The buttons sit beside each workload on a <Page to="/services">service</Page> page.
            Every action is checked with the cluster first, so you can see what would happen before
            you confirm, including which pods would go and how long they have been running.
          </p>
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="w-full min-w-[28rem] border-collapse text-xs">
              <thead>
                <tr className="border-b border-line bg-cream text-left text-muted">
                  <th className="px-3 py-2 font-medium">Action</th>
                  <th className="px-3 py-2 font-medium">What it does</th>
                </tr>
              </thead>
              <tbody className="bg-panel">
                <Row name="Scale">Change the replica count, one at a time.</Row>
                <Row name="Stop">
                  Scale to 0 and remember the previous count, so you can put it back.
                </Row>
                <Row name="Kill">Scale to 0 and delete the running pods straight away.</Row>
                <Row name="Restart">Replace the pods one at a time, with no downtime.</Row>
                <Row name="Kill service">Kill every workload belonging to the service at once.</Row>
              </tbody>
            </table>
          </div>
          <p>
            Anything that takes a service to 0 asks you to type the workload name and tick a box
            before it will run.
          </p>
        </Section>

        <Section id="pods" title="Kill a pod">
          <p>
            Open a pod from <Page to="/pods">Pods</Page>, or from the service it belongs to.
            Deleting a pod bounces that one replica, and Kubernetes starts a replacement within a
            second. Use <span className="font-medium">Stop</span> when you want the service to go
            away.
          </p>
          <p>Killing a single container deletes the whole pod it runs in.</p>
        </Section>

        <Section id="restore" title="Restore a stopped service">
          <p>
            A workload sitting at 0 replicas gets a restore banner on its service page. If you
            stopped it here, the banner offers the replica count it had before. If it was stopped
            some other way, the banner says the old count is unknown and offers to restore 1.
          </p>
          <p>
            Kill still works on a stopped workload. Use it to clear away any pods that are hanging
            around.
          </p>
        </Section>

        <Section id="database" title="Resize the database">
          <p>
            Use the <Page to="/database">Database</Page> page. Scale buttons stay hidden for
            database members everywhere else in the app, because the Arango operator manages
            them.
          </p>
          <ul className="list-disc space-y-1.5 pl-4">
            <li>Coordinators and gateways can be scaled up or down.</li>
            <li>
              Shrinking dbservers shows a warning first, since the operator has to move shards off
              them.
            </li>
            <li>Agents are fixed once the cluster has been created.</li>
          </ul>
          <p>
            Resizing stays switched off until <code>ARM_ALLOW_DATABASE_SCALING=true</code> is set
            where the API runs.
          </p>
        </Section>

        <Section id="genai" title="GenAI projects">
          <p>
            <Page to="/genai">GenAI</Page> pairs AutoGraph and GraphRAG retriever releases with the
            project they serve.
          </p>
          <p>
            Retrievers with no project service are usually left over from a project that has gone
            away, so they are good candidates to stop. A project the tool could not identify takes
            its name from a secret, which the tool does not read.
          </p>
        </Section>

        <Section id="missing" title="When a button is missing">
          <ul className="list-disc space-y-1.5 pl-4">
            <li>
              <span className="font-medium">Protected:</span> the ArangoDB operator owns this
              workload. Resize it from <Page to="/database">Database</Page>.
            </li>
            <li>
              <span className="font-medium">Guarded:</span> platform infrastructure, available once{' '}
              <code>ARM_ALLOW_GUARDED_ACTIONS=true</code> is set.
            </li>
            <li>
              <span className="font-medium">Greyed out:</span> the app is in read-only mode. Hover
              a button to see why it is disabled.
            </li>
            <li>
              <span className="font-medium">Empty panel:</span> the credential is missing a
              permission. <Page to="/settings">Settings</Page> lists what it can read.
            </li>
          </ul>
        </Section>

        <Section id="safety" title="Safety settings">
          <p>
            Three settings control what the app is allowed to change. They are set where the API
            runs, and <Page to="/settings">Settings</Page> shows the current values.
          </p>
          <ul className="list-disc space-y-1.5 pl-4">
            <li>
              <code>ARM_READ_ONLY</code> blocks every change.
            </li>
            <li>
              <code>ARM_ALLOW_GUARDED_ACTIONS</code> allows actions on platform infrastructure.
            </li>
            <li>
              <code>ARM_ALLOW_DATABASE_SCALING</code> allows database tiers to be resized.
            </li>
          </ul>
          <p>
            Workloads owned by the operator stay protected whatever these are set to. Every change
            you make is logged on <Page to="/activity">Activity</Page>.
          </p>
        </Section>

        <Section id="pages" title="The pages">
          <dl className="space-y-2">
            <Term name={<Page to="/">Overview</Page>}>
              Totals for the namespace, plus anything that needs attention.
            </Term>
            <Term name={<Page to="/services">Services</Page>}>
              Everything running here, with the buttons to act on it.
            </Term>
            <Term name={<Page to="/genai">GenAI</Page>}>
              AutoGraph and GraphRAG releases, grouped by project.
            </Term>
            <Term name={<Page to="/pods">Pods</Page>}>
              Every pod, sortable. Open one to read its logs.
            </Term>
            <Term name={<Page to="/capacity">Capacity</Page>}>
              Where the capacity is going, and what can be freed.
            </Term>
            <Term name={<Page to="/database">Database</Page>}>
              Resize coordinators, dbservers and gateways.
            </Term>
            <Term name={<Page to="/activity">Activity</Page>}>
              A log of every change made through this tool.
            </Term>
            <Term name={<Page to="/settings">Settings</Page>}>
              Budget, safety settings and what the credential can read.
            </Term>
          </dl>
        </Section>
      </div>
    </div>
  )
}

function jumpTo(event: MouseEvent<HTMLAnchorElement>, id: string) {
  event.preventDefault()
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const url = `${window.location.pathname}${window.location.search}#${id}`
  window.history.replaceState(null, '', url)
}

function TocLink({ id, children }: { id: string; children: string }) {
  return (
    <a
      href={`#${id}`}
      onClick={(event) => jumpTo(event, id)}
      className="text-xs text-muted hover:text-arango"
    >
      {children}
    </a>
  )
}

function Section({
  id,
  title,
  children,
}: {
  id: string
  title: string
  children: ReactNode
}) {
  return (
    <Card className="scroll-mt-2 p-4">
      <h3 id={id} className="text-sm font-semibold text-body">
        {title}
      </h3>
      <div className="mt-2 max-w-prose space-y-2 text-xs text-body [&_code]:font-mono [&_code]:text-[11px]">
        {children}
      </div>
    </Card>
  )
}

function Term({ name, children }: { name: ReactNode; children: ReactNode }) {
  return (
    <div>
      <dt className="font-medium text-body">{name}</dt>
      <dd className="text-muted">{children}</dd>
    </div>
  )
}

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <tr className="border-b border-line/60 last:border-0">
      <td className="px-3 py-2 align-top font-medium text-body">{name}</td>
      <td className="px-3 py-2 text-muted">{children}</td>
    </tr>
  )
}

function Page({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-arango hover:underline">
      {children}
    </Link>
  )
}
