using System;
using StudioB.Containers;
using Xunit;

namespace StudioB.Containers.Tests
{
    public class ContainerTimelineBuilderTests
    {
        // ---------------------------------------------------------------
        // Hybrid PO-lifecycle timeline: 8 stages
        // PLACED → ACKED → FACTORY READY → SHIPPED → IN TRANSIT →
        // ARRIVED PORT → CUSTOMS → DELIVERED
        // ---------------------------------------------------------------

        [Fact]
        public void Build_WithPODates_Shows_PlacedAckedFactoryReady()
        {
            var data = new ContainerTimelineBuilder.TimelineData
            {
                Status = "BOOKED",
                OrderDate = new DateTime(2026, 1, 10),
                AcknowledgedDate = new DateTime(2026, 1, 15),
                FactoryReadyDate = new DateTime(2026, 2, 20),
            };

            string html = ContainerTimelineBuilder.Build(data);

            Assert.Contains("PLACED", html);
            Assert.Contains("ACKED", html);
            Assert.Contains("FACTORY READY", html);
            Assert.Contains("Jan 10", html);
            Assert.Contains("Jan 15", html);
            Assert.Contains("Feb 20", html);
        }

        [Fact]
        public void Build_WithPODates_Shows_AllEightStages()
        {
            var data = new ContainerTimelineBuilder.TimelineData
            {
                Status = "DELIVERED",
                OrderDate = new DateTime(2026, 1, 10),
                AcknowledgedDate = new DateTime(2026, 1, 15),
                FactoryReadyDate = new DateTime(2026, 2, 20),
                DepartedDate = new DateTime(2026, 3, 1),
                ArrivedPortDate = new DateTime(2026, 4, 1),
                CustomsReleasedDate = new DateTime(2026, 4, 3),
                DeliveredDate = new DateTime(2026, 4, 5),
            };

            string html = ContainerTimelineBuilder.Build(data);

            Assert.Contains("PLACED", html);
            Assert.Contains("ACKED", html);
            Assert.Contains("FACTORY READY", html);
            Assert.Contains("SHIPPED", html);
            Assert.Contains("IN TRANSIT", html);
            Assert.Contains("ARRIVED PORT", html);
            Assert.Contains("CUSTOMS", html);
            Assert.Contains("DELIVERED", html);
        }

        [Fact]
        public void Build_WithoutPODates_ShowsPendingForFirstThreeStages()
        {
            var data = new ContainerTimelineBuilder.TimelineData
            {
                Status = "IN_TRANSIT",
                DepartedDate = new DateTime(2026, 3, 1),
                ETA = new DateTime(2026, 4, 15),
            };

            string html = ContainerTimelineBuilder.Build(data);

            // First 3 stages should still render (pending / gray)
            Assert.Contains("PLACED", html);
            Assert.Contains("ACKED", html);
            Assert.Contains("FACTORY READY", html);
            // Container stages should show
            Assert.Contains("SHIPPED", html);
            Assert.Contains("IN TRANSIT", html);
        }

        [Fact]
        public void Build_CurrentStatus_Booked_MapsToPlaced()
        {
            var data = new ContainerTimelineBuilder.TimelineData
            {
                Status = "BOOKED",
                OrderDate = new DateTime(2026, 1, 10),
            };

            string html = ContainerTimelineBuilder.Build(data);
            // PLACED should be marked as current (tl-current class)
            Assert.Contains("tl-current", html);
            Assert.Contains("PLACED", html);
        }

        [Fact]
        public void Build_CustomsHold_ShowsAlertOnCustomsStage()
        {
            var data = new ContainerTimelineBuilder.TimelineData
            {
                Status = "CUSTOMS_HOLD",
                OrderDate = new DateTime(2026, 1, 10),
                AcknowledgedDate = new DateTime(2026, 1, 15),
                FactoryReadyDate = new DateTime(2026, 2, 20),
                DepartedDate = new DateTime(2026, 3, 1),
                ArrivedPortDate = new DateTime(2026, 4, 1),
                CustomsHoldDays = 5,
            };

            string html = ContainerTimelineBuilder.Build(data);
            Assert.Contains("tl-alert", html);
        }

        [Fact]
        public void Build_Connectors_CompleteUpToCurrentStage()
        {
            var data = new ContainerTimelineBuilder.TimelineData
            {
                Status = "IN_TRANSIT",
                OrderDate = new DateTime(2026, 1, 10),
                AcknowledgedDate = new DateTime(2026, 1, 15),
                FactoryReadyDate = new DateTime(2026, 2, 20),
                DepartedDate = new DateTime(2026, 3, 1),
            };

            string html = ContainerTimelineBuilder.Build(data);
            // Connectors up to current stage should be complete
            Assert.Contains("tl-connector-complete", html);
        }
    }
}
