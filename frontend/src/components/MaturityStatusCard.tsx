import { ArrowDownCircle, ArrowRightCircle, ArrowUpCircle, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { MaturityStatusCard as MaturityStatusCardData } from '../types';

interface MaturityStatusCardProps {
  card?: MaturityStatusCardData;
}

const MaturityStatusCard = ({ card }: MaturityStatusCardProps) => {
  if (!card) {
    return (
      <div className="card">
        <h3 className="text-lg font-semibold mb-2 text-merlin-blue">Maturity Status</h3>
        <p className="text-sm text-dark-muted">No maturity readiness artifact available yet.</p>
      </div>
    );
  }

  const readinessColor =
    card.readiness_status === 'promotion_ready'
      ? 'text-green-400'
      : card.readiness_status === 'demotion_required'
        ? 'text-red-400'
        : 'text-yellow-400';
  const regressionColor =
    card.regression_status === 'stable' ? 'text-green-400' : 'text-red-400';

  const actionIcon =
    card.recommended_action === 'promote' ? (
      <ArrowUpCircle className="w-5 h-5 text-green-400" />
    ) : card.recommended_action === 'demote' ? (
      <ArrowDownCircle className="w-5 h-5 text-red-400" />
    ) : (
      <ArrowRightCircle className="w-5 h-5 text-yellow-400" />
    );

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-merlin-blue">Maturity Status</h3>
          <p className="text-xs text-dark-muted">Policy: {card.policy_version}</p>
        </div>
        {card.regression_status === 'stable' ? (
          <ShieldCheck className="w-6 h-6 text-green-400" />
        ) : (
          <ShieldAlert className="w-6 h-6 text-red-400" />
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div>
          <p className="text-xs text-dark-muted">Tier</p>
          <p className="text-xl font-bold">{card.tier}</p>
        </div>
        <div>
          <p className="text-xs text-dark-muted">Readiness</p>
          <p className={`font-semibold ${readinessColor}`}>{card.readiness_status}</p>
        </div>
        <div>
          <p className="text-xs text-dark-muted">Regression</p>
          <p className={`font-semibold ${regressionColor}`}>{card.regression_status}</p>
        </div>
        <div>
          <p className="text-xs text-dark-muted">Recommendation</p>
          <div className="flex items-center gap-2">
            {actionIcon}
            <p className="font-semibold">
              {card.recommended_action} {card.recommended_tier}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-dark-border grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <div>
          <span className="text-dark-muted">Critical failures:</span>{' '}
          <span className="font-semibold">{card.critical_failure_count}</span>
        </div>
        <div>
          <span className="text-dark-muted">Missing promotion gates:</span>{' '}
          <span className="font-semibold">{card.missing_promotion_gate_count}</span>
        </div>
        <div className="truncate">
          <span className="text-dark-muted">Report timestamp:</span>{' '}
          <span className="font-semibold">{card.report_generated_at || 'n/a'}</span>
        </div>
      </div>
    </div>
  );
};

export default MaturityStatusCard;
