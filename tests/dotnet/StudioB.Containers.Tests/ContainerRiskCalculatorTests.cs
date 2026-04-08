using System;
using StudioB.Containers;
using Xunit;

namespace StudioB.Containers.Tests
{
    public class ContainerRiskCalculatorTests
    {
        private static readonly DateTime Today = new DateTime(2026, 4, 7);

        // ---------------------------------------------------------------
        // ComputeRiskLevel — CRITICAL triggers
        // ---------------------------------------------------------------

        [Fact]
        public void Critical_When_LastFreeDay_Is_In_The_Past()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "ARRIVED",
                lastFreeDay: Today.AddDays(-1),
                eta: Today.AddDays(-3),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskCritical, result);
        }

        [Fact]
        public void Critical_When_CustomsHold_Exceeds_Two_Days()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "CUSTOMS_HOLD",
                lastFreeDay: Today.AddDays(5),
                eta: Today.AddDays(-1),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 0,
                customsHoldDays: 3);

            Assert.Equal(ContainerRiskCalculator.RiskCritical, result);
        }

        [Fact]
        public void Critical_When_ISF_Not_Filed_And_Close_To_Departure()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "BOOKED",
                lastFreeDay: null,
                eta: Today.AddDays(10),
                isfFiledDate: null,
                departedDate: null,
                docsRequired: 3,
                docsReceived: 3,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskCritical, result);
        }

        [Fact]
        public void Critical_When_Docs_Incomplete_And_Arrival_Imminent()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "IN_TRANSIT",
                lastFreeDay: Today.AddDays(10),
                eta: Today.AddDays(2),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 3,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskCritical, result);
        }

        // ---------------------------------------------------------------
        // ComputeRiskLevel — WARNING triggers
        // ---------------------------------------------------------------

        [Fact]
        public void Warning_When_LastFreeDay_Within_Three_Days()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "ARRIVED",
                lastFreeDay: Today.AddDays(2),
                eta: Today.AddDays(-1),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskWarning, result);
        }

        [Fact]
        public void Warning_When_ETA_Within_Seven_Days_And_Not_Delivered()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "IN_TRANSIT",
                lastFreeDay: Today.AddDays(30),
                eta: Today.AddDays(5),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskWarning, result);
        }

        [Fact]
        public void Warning_When_ETA_Changed_Twice_Or_More_Recently()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "IN_TRANSIT",
                lastFreeDay: Today.AddDays(30),
                eta: Today.AddDays(15),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 2,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskWarning, result);
        }

        [Fact]
        public void Warning_When_Docs_Incomplete_With_Plenty_Of_Time()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "IN_TRANSIT",
                lastFreeDay: Today.AddDays(30),
                eta: Today.AddDays(15),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 3,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskWarning, result);
        }

        // ---------------------------------------------------------------
        // ComputeRiskLevel — OK (happy path)
        // ---------------------------------------------------------------

        [Fact]
        public void Ok_When_All_Clean_And_Far_Out()
        {
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "IN_TRANSIT",
                lastFreeDay: Today.AddDays(30),
                eta: Today.AddDays(20),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskOk, result);
        }

        [Fact]
        public void Ok_With_No_LFD_Set_Yet_And_ETA_Far_Out()
        {
            // A newly-booked container shouldn't be CRITICAL just because
            // dates haven't been populated.
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "BOOKED",
                lastFreeDay: null,
                eta: Today.AddDays(45),
                isfFiledDate: null,
                departedDate: null,
                docsRequired: 0,
                docsReceived: 0,
                etaChangesLast7Days: 0,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskOk, result);
        }

        // ---------------------------------------------------------------
        // Priority ordering — CRITICAL wins over WARNING conditions
        // ---------------------------------------------------------------

        [Fact]
        public void Critical_Trumps_Warning_When_Both_Apply()
        {
            // Past LFD (critical) + ETA within 7 days (warning) → CRITICAL
            var result = ContainerRiskCalculator.ComputeRiskLevel(
                today: Today,
                status: "ARRIVED",
                lastFreeDay: Today.AddDays(-2),
                eta: Today.AddDays(3),
                isfFiledDate: Today.AddDays(-20),
                departedDate: Today.AddDays(-15),
                docsRequired: 5,
                docsReceived: 5,
                etaChangesLast7Days: 3,
                customsHoldDays: 0);

            Assert.Equal(ContainerRiskCalculator.RiskCritical, result);
        }

        // ---------------------------------------------------------------
        // ComputeDemurrageExposure
        // ---------------------------------------------------------------

        [Fact]
        public void Exposure_Zero_When_No_LFD_Set()
        {
            var result = ContainerRiskCalculator.ComputeDemurrageExposure(
                today: Today,
                lastFreeDay: null,
                demurrageDailyRate: 200m,
                customsHoldDays: 0,
                customsHoldEstimatedCostPerDay: null);

            Assert.Equal(0m, result);
        }

        [Fact]
        public void Exposure_Zero_When_LFD_Is_In_Future_Beyond_Horizon()
        {
            // LFD is 10 days away, horizon is 7 — no exposure this week
            var result = ContainerRiskCalculator.ComputeDemurrageExposure(
                today: Today,
                lastFreeDay: Today.AddDays(10),
                demurrageDailyRate: 200m,
                customsHoldDays: 0,
                customsHoldEstimatedCostPerDay: null);

            Assert.Equal(0m, result);
        }

        [Fact]
        public void Exposure_Accrues_For_Days_Within_Horizon_At_Normal_Rate()
        {
            // LFD was yesterday. Today + next 6 days = 7 days at $200 = $1400
            // (day of LFD itself is not charged; first billable day is LFD+1)
            // Actually looking at the impl: it charges day-by-day for d = 0..
            // where d=0 is LFD itself. So LFD yesterday = d=1 charged today,
            // and days 2..7 charged for next 6 days — 7 days total in horizon.
            var result = ContainerRiskCalculator.ComputeDemurrageExposure(
                today: Today,
                lastFreeDay: Today.AddDays(-1),
                demurrageDailyRate: 200m,
                customsHoldDays: 0,
                customsHoldEstimatedCostPerDay: null);

            // 7 days in the [today, today+7) horizon. All within the first 7
            // days past LFD → normal rate. 7 * $200 = $1400.
            Assert.Equal(1400m, result);
        }

        [Fact]
        public void Exposure_Escalates_After_Seven_Days_Past_LFD()
        {
            // LFD was 8 days ago. All 7 days in horizon are past day 7 → 1.5x
            // 7 * $200 * 1.5 = $2100
            var result = ContainerRiskCalculator.ComputeDemurrageExposure(
                today: Today,
                lastFreeDay: Today.AddDays(-8),
                demurrageDailyRate: 200m,
                customsHoldDays: 0,
                customsHoldEstimatedCostPerDay: null);

            Assert.Equal(2100m, result);
        }

        [Fact]
        public void Exposure_Adds_Customs_Hold_Cost_When_Provided()
        {
            var result = ContainerRiskCalculator.ComputeDemurrageExposure(
                today: Today,
                lastFreeDay: null,
                demurrageDailyRate: null,
                customsHoldDays: 3,
                customsHoldEstimatedCostPerDay: 150m);

            Assert.Equal(450m, result);
        }

        [Fact]
        public void Exposure_Rounds_To_Two_Decimals()
        {
            // Use a rate that would otherwise drift past 2dp
            var result = ContainerRiskCalculator.ComputeDemurrageExposure(
                today: Today,
                lastFreeDay: Today.AddDays(-1),
                demurrageDailyRate: 123.456m,
                customsHoldDays: 0,
                customsHoldEstimatedCostPerDay: null);

            // 7 days * 123.456 = 864.192 → rounded to 864.19
            Assert.Equal(864.19m, result);
        }

        // ---------------------------------------------------------------
        // CustomsHoldDays
        // ---------------------------------------------------------------

        [Fact]
        public void CustomsHoldDays_Zero_When_Not_In_Hold_Status()
        {
            var result = ContainerRiskCalculator.CustomsHoldDays(
                Today, "IN_TRANSIT", Today.AddDays(-10));
            Assert.Equal(0, result);
        }

        [Fact]
        public void CustomsHoldDays_Zero_When_LastSyncDate_Missing()
        {
            var result = ContainerRiskCalculator.CustomsHoldDays(
                Today, "CUSTOMS_HOLD", null);
            Assert.Equal(0, result);
        }

        [Fact]
        public void CustomsHoldDays_Measures_Days_Since_LastSync()
        {
            var result = ContainerRiskCalculator.CustomsHoldDays(
                Today, "CUSTOMS_HOLD", Today.AddDays(-5));
            Assert.Equal(5, result);
        }

        [Fact]
        public void CustomsHoldDays_Floor_Is_Zero()
        {
            // Edge case: last sync is in the future somehow
            var result = ContainerRiskCalculator.CustomsHoldDays(
                Today, "CUSTOMS_HOLD", Today.AddDays(1));
            Assert.Equal(0, result);
        }
    }
}
