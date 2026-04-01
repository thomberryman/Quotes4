"use client";

import { useQuery } from "@tanstack/react-query";

import { getBrowserApiClient } from "../lib/api/browser-client";

const api = getBrowserApiClient();

export function RecentJobsPanel() {
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => {
      return api.listJobs({ limit: 5 });
    }
  });
  const failedCount = jobsQuery.data?.summary.counts.failed ?? 0;

  return (
    <article className="panel">
      <h3>Recent Jobs</h3>
      {jobsQuery.isLoading ? <p>Loading recent queue activity.</p> : null}
      {jobsQuery.isError ? <p>Queue activity will appear here when the API is reachable.</p> : null}

      {jobsQuery.data ? (
        <div className="stack">
          {failedCount > 0 ? (
            <p>{failedCount} failed job(s) need review.</p>
          ) : null}
          {jobsQuery.data.items.length > 0 ? (
            jobsQuery.data.items.map((job) => (
              <div className="status-row" key={job.id}>
                <div>
                  <strong>{job.queueName}</strong>
                  <p>{job.status}{job.lastError ? `: ${job.lastError}` : ""}</p>
                </div>
                <span className="status-pill">{job.relatedEntityId ?? "scaffold"}</span>
              </div>
            ))
          ) : (
            <p>No jobs have been queued yet.</p>
          )}
        </div>
      ) : null}
    </article>
  );
}
