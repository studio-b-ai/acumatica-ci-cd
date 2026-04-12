using System;
using System.Collections.Generic;

namespace StudioB.Containers
{
    /// <summary>
    /// Pure logic for computing a container's risk level and demurrage exposure.
    /// Kept separate from ContainerMaint so it can be unit-tested without the PXGraph dependency.
    /// </summary>
    public static class ContainerRiskCalculator
    {
        public const string RiskCritical = "R";
        public const string RiskWarning  = "A";
        public const string RiskOk       = "G";

        /// <summary>
        /// Computes a container's risk level based on status, LFD, documents, and ISF filing.
        /// CRITICAL if past LFD, customs hold > 2d, ISF missing and departed, or docs incomplete
        /// with imminent arrival. WARNING if LFD soon, ETA soon, ETA slipped, or docs incomplete.
        /// </summary>
        public static string ComputeRiskLevel(
            DateTime today,
            string status,
            DateTime? lastFreeDay,
            DateTime? eta,
            DateTime? isfFiledDate,
            DateTime? departedDate,
            int docsRequired,
            int docsReceived,
            int etaChangesLast7Days,
            int customsHoldDays)
        {
            // ----- CRITICAL triggers -----
            if (lastFreeDay.HasValue && lastFreeDay.Value.Date < today.Date)
                return RiskCritical;

            if (status == "CUSTOMS_HOLD" && customsHoldDays > 2)
                return RiskCritical;

            // ISF must be filed 24h before foreign load. If container is past the booking stage
            // and approaching departure without ISF, that's critical.
            if (!isfFiledDate.HasValue &&
                !departedDate.HasValue &&
                status == "BOOKED" &&
                eta.HasValue && (eta.Value.Date - today.Date).TotalDays < 14)
                return RiskCritical;

            if (docsRequired > 0 && docsReceived < docsRequired &&
                eta.HasValue && (eta.Value.Date - today.Date).TotalDays <= 3)
                return RiskCritical;

            // ----- WARNING triggers -----
            if (lastFreeDay.HasValue && (lastFreeDay.Value.Date - today.Date).TotalDays <= 3)
                return RiskWarning;

            if (eta.HasValue && (eta.Value.Date - today.Date).TotalDays <= 7 &&
                status != "DELIVERED" && status != "CANCELLED")
                return RiskWarning;

            if (etaChangesLast7Days >= 2)
                return RiskWarning;

            if (docsRequired > 0 && docsReceived < docsRequired)
                return RiskWarning;

            return RiskOk;
        }

        /// <summary>
        /// Computes projected demurrage exposure over next 7 days.
        /// Adds escalation multiplier (1.5x) for days past LFD+7.
        /// </summary>
        public static decimal ComputeDemurrageExposure(
            DateTime today,
            DateTime? lastFreeDay,
            decimal? demurrageDailyRate,
            int customsHoldDays,
            decimal? customsHoldEstimatedCostPerDay)
        {
            decimal exposure = 0m;
            if (lastFreeDay.HasValue && demurrageDailyRate.HasValue && demurrageDailyRate.Value > 0m)
            {
                DateTime lfd = lastFreeDay.Value.Date;
                DateTime horizon = today.Date.AddDays(7);

                // Days past LFD already accrued (if negative, none)
                int daysAlreadyPast = Math.Max(0, (int)(today.Date - lfd).TotalDays);
                int daysProjected   = (int)(horizon - today.Date).TotalDays;

                // Day-by-day: d is the 1-based day-past-LFD index.
                // Days 1..7 past LFD charge normal rate.
                // Day 8 and beyond charge 1.5x (escalation convention for HF).
                // d=0 is LFD itself (the last free day) and is never charged.
                for (int d = 1; d <= daysAlreadyPast + daysProjected; d++)
                {
                    DateTime dayBeingCharged = lfd.AddDays(d);
                    if (dayBeingCharged >= today.Date && dayBeingCharged < horizon)
                    {
                        decimal rate = demurrageDailyRate.Value;
                        if (d >= 8) rate = rate * 1.5m;
                        exposure += rate;
                    }
                }
            }

            if (customsHoldDays > 0 && customsHoldEstimatedCostPerDay.HasValue)
            {
                exposure += customsHoldDays * customsHoldEstimatedCostPerDay.Value;
            }

            return Math.Round(exposure, 2);
        }

        /// <summary>
        /// Returns the number of days the container has been in customs hold.
        /// </summary>
        public static int CustomsHoldDays(DateTime today, string status, DateTime? lastSyncDate)
        {
            if (status != "CUSTOMS_HOLD") return 0;
            if (!lastSyncDate.HasValue) return 0;
            int days = (int)(today.Date - lastSyncDate.Value.Date).TotalDays;
            return days < 0 ? 0 : days;
        }
    }
}
