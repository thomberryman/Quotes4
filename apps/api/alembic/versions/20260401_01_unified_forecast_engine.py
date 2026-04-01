"""extend forecast tables for unified forecast engine metadata

Revision ID: 20260401_01_unified_forecast
Revises: 20260331_03_prediction_runs
Create Date: 2026-04-01 11:15:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260401_01_unified_forecast"
down_revision = "20260331_03_prediction_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forecast_versions", sa.Column("scenario_key", sa.String(length=32), nullable=False, server_default="base"))
    op.add_column("forecast_versions", sa.Column("engine_source", sa.String(length=100), nullable=False, server_default="unified_forecast_engine"))
    op.add_column("forecast_versions", sa.Column("prediction_run_id", sa.String(length=32), nullable=True))
    op.add_column("forecast_versions", sa.Column("prediction_scenario_key", sa.String(length=32), nullable=True))
    op.add_column("forecast_versions", sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("forecast_versions", sa.Column("data_sufficiency_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("forecast_versions", sa.Column("fallback_tier", sa.String(length=100), nullable=True))
    op.add_column("forecast_versions", sa.Column("explanation_summary", sa.JSON(), nullable=True))
    op.add_column("forecast_versions", sa.Column("change_summary", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_forecast_versions_prediction_run_id_prediction_runs",
        "forecast_versions",
        "prediction_runs",
        ["prediction_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("forecast_versions", "scenario_key", server_default=None)
    op.alter_column("forecast_versions", "engine_source", server_default=None)

    op.add_column("forecast_lines", sa.Column("forecast_method_key", sa.String(length=32), nullable=True))
    op.add_column("forecast_lines", sa.Column("allocation_profile_key", sa.String(length=32), nullable=True))
    op.add_column("forecast_lines", sa.Column("sequencing_template_key", sa.String(length=64), nullable=True))
    op.add_column("forecast_lines", sa.Column("sequencing_stage_key", sa.String(length=64), nullable=True))
    op.add_column("forecast_lines", sa.Column("overlap_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("forecast_lines", sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("forecast_lines", sa.Column("data_sufficiency_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("forecast_lines", sa.Column("fallback_tier", sa.String(length=100), nullable=True))
    op.add_column("forecast_lines", sa.Column("actuals_to_date_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("forecast_lines", sa.Column("remaining_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("forecast_lines", sa.Column("forecast_inputs", sa.JSON(), nullable=True))
    op.add_column("forecast_lines", sa.Column("explanation_json", sa.JSON(), nullable=True))

    op.add_column("monthly_forecast_allocations", sa.Column("low_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("monthly_forecast_allocations", sa.Column("high_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("monthly_forecast_allocations", sa.Column("actual_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("monthly_forecast_allocations", sa.Column("allocation_source", sa.String(length=32), nullable=True))
    op.add_column("monthly_forecast_allocations", sa.Column("source_context", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("monthly_forecast_allocations", "source_context")
    op.drop_column("monthly_forecast_allocations", "allocation_source")
    op.drop_column("monthly_forecast_allocations", "actual_amount")
    op.drop_column("monthly_forecast_allocations", "high_amount")
    op.drop_column("monthly_forecast_allocations", "low_amount")

    op.drop_column("forecast_lines", "explanation_json")
    op.drop_column("forecast_lines", "forecast_inputs")
    op.drop_column("forecast_lines", "remaining_amount")
    op.drop_column("forecast_lines", "actuals_to_date_amount")
    op.drop_column("forecast_lines", "fallback_tier")
    op.drop_column("forecast_lines", "data_sufficiency_score")
    op.drop_column("forecast_lines", "confidence_score")
    op.drop_column("forecast_lines", "overlap_percent")
    op.drop_column("forecast_lines", "sequencing_stage_key")
    op.drop_column("forecast_lines", "sequencing_template_key")
    op.drop_column("forecast_lines", "allocation_profile_key")
    op.drop_column("forecast_lines", "forecast_method_key")

    op.drop_constraint(
        "fk_forecast_versions_prediction_run_id_prediction_runs",
        "forecast_versions",
        type_="foreignkey",
    )
    op.drop_column("forecast_versions", "change_summary")
    op.drop_column("forecast_versions", "explanation_summary")
    op.drop_column("forecast_versions", "fallback_tier")
    op.drop_column("forecast_versions", "data_sufficiency_score")
    op.drop_column("forecast_versions", "confidence_score")
    op.drop_column("forecast_versions", "prediction_scenario_key")
    op.drop_column("forecast_versions", "prediction_run_id")
    op.drop_column("forecast_versions", "engine_source")
    op.drop_column("forecast_versions", "scenario_key")
