using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container")]
    public class UsrContainer : PXBqlTable, IBqlTable
    {
        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBIdentity]
        public int? ContainerID { get; set; }
        #endregion

        #region ContainerCD
        public abstract class containerCD : BqlString.Field<containerCD> { }
        [PXDBString(20, IsUnicode = true, IsKey = true, InputMask = "")]
        [PXDefault]
        [PXUIField(DisplayName = "Container Nbr", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrContainer.containerCD>),
            typeof(UsrContainer.containerCD),
            typeof(UsrContainer.carrierCode),
            typeof(UsrContainer.status),
            typeof(UsrContainer.vesselName),
            typeof(UsrContainer.eta))]
        public string ContainerCD { get; set; }
        #endregion

        #region CarrierCode
        public abstract class carrierCode : BqlString.Field<carrierCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Carrier")]
        [PXStringList(new string[] { "MAERSK", "CHR", "OTS", "OTHER" },
                       new string[] { "Maersk", "CH Robinson", "OTS", "Other" })]
        public string CarrierCode { get; set; }
        #endregion

        #region BookingRef
        public abstract class bookingRef : BqlString.Field<bookingRef> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Booking Ref")]
        public string BookingRef { get; set; }
        #endregion

        #region BillOfLading
        public abstract class billOfLading : BqlString.Field<billOfLading> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Bill of Lading")]
        public string BillOfLading { get; set; }
        #endregion

        #region VesselName
        public abstract class vesselName : BqlString.Field<vesselName> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Vessel")]
        public string VesselName { get; set; }
        #endregion

        #region VesselIMO
        public abstract class vesselIMO : BqlString.Field<vesselIMO> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "IMO #")]
        public string VesselIMO { get; set; }
        #endregion

        #region VoyageNbr
        public abstract class voyageNbr : BqlString.Field<voyageNbr> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Voyage #")]
        public string VoyageNbr { get; set; }
        #endregion

        #region PortOfLoading
        public abstract class portOfLoading : BqlString.Field<portOfLoading> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Port of Loading")]
        [PXSelector(typeof(Search<UsrPort.portCode,
            Where<UsrPort.active, Equal<True>>>),
            typeof(UsrPort.portCode),
            typeof(UsrPort.portName),
            typeof(UsrPort.country))]
        public string PortOfLoading { get; set; }
        #endregion

        #region PortOfDischarge
        public abstract class portOfDischarge : BqlString.Field<portOfDischarge> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Port of Discharge")]
        [PXSelector(typeof(Search<UsrPort.portCode,
            Where<UsrPort.active, Equal<True>>>),
            typeof(UsrPort.portCode),
            typeof(UsrPort.portName),
            typeof(UsrPort.country))]
        public string PortOfDischarge { get; set; }
        #endregion

        #region ETD
        public abstract class etd : BqlDateTime.Field<etd> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Est. Departure")]
        public DateTime? ETD { get; set; }
        #endregion

        #region ATD
        public abstract class atd : BqlDateTime.Field<atd> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Act. Departure")]
        public DateTime? ATD { get; set; }
        #endregion

        #region ETA
        public abstract class eta : BqlDateTime.Field<eta> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Est. Arrival")]
        public DateTime? ETA { get; set; }
        #endregion

        #region ATA
        public abstract class ata : BqlDateTime.Field<ata> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Act. Arrival")]
        public DateTime? ATA { get; set; }
        #endregion

        #region Status
        public abstract class status : BqlString.Field<status> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault("BOOKED")]
        [PXUIField(DisplayName = "Status")]
        [PXStringList(new string[] { "BOOKED", "DEPARTED", "IN_TRANSIT", "ARRIVED", "DISCHARGED", "CUSTOMS_HOLD", "GATED_OUT", "DELIVERED", "CANCELLED" },
                       new string[] { "Booked", "Departed", "In Transit", "Arrived", "Discharged", "Customs Hold", "Gated Out", "Delivered", "Cancelled" })]
        public string Status { get; set; }
        #endregion

        #region TransportMode
        public abstract class transportMode : BqlString.Field<transportMode> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Transport Mode")]
        [PXStringList(new string[] { "OCEAN", "AIR", "RAIL", "TRUCK" },
                       new string[] { "Ocean", "Air", "Rail", "Truck" })]
        public string TransportMode { get; set; }
        #endregion

        #region ContainerType
        public abstract class containerType : BqlString.Field<containerType> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Type")]
        [PXSelector(typeof(Search<UsrContainerType.typeCD,
            Where<UsrContainerType.active, Equal<True>>>),
            typeof(UsrContainerType.typeCD),
            typeof(UsrContainerType.description))]
        public string ContainerType { get; set; }
        #endregion

        #region SealNbr
        public abstract class sealNbr : BqlString.Field<sealNbr> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Seal #")]
        public string SealNbr { get; set; }
        #endregion

        #region LandedCostRefNbr
        public abstract class landedCostRefNbr : BqlString.Field<landedCostRefNbr> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "Landed Cost Ref", Enabled = false)]
        public string LandedCostRefNbr { get; set; }
        #endregion

        #region LandedCostStatus
        public abstract class landedCostStatus : BqlString.Field<landedCostStatus> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Status", Enabled = false)]
        public string LandedCostStatus { get; set; }
        #endregion

        #region LastEventCode
        public abstract class lastEventCode : BqlString.Field<lastEventCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Last Event", Enabled = false)]
        public string LastEventCode { get; set; }
        #endregion

        #region LastEventDate
        public abstract class lastEventDate : BqlDateTime.Field<lastEventDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Last Event Date", Enabled = false)]
        public DateTime? LastEventDate { get; set; }
        #endregion

        #region LastSyncDate
        public abstract class lastSyncDate : BqlDateTime.Field<lastSyncDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Last Sync", Enabled = false)]
        public DateTime? LastSyncDate { get; set; }
        #endregion

        // --- 2026-04-07: Command Center redesign (RFC 1 Phase A) ---
        // Milestone timestamps for status timeline strip
        #region BookedDate
        public abstract class bookedDate : BqlDateTime.Field<bookedDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Booked On")]
        public DateTime? BookedDate { get; set; }
        #endregion

        #region DepartedDate
        public abstract class departedDate : BqlDateTime.Field<departedDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Departed On")]
        public DateTime? DepartedDate { get; set; }
        #endregion

        #region ArrivedPortDate
        public abstract class arrivedPortDate : BqlDateTime.Field<arrivedPortDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Arrived Port")]
        public DateTime? ArrivedPortDate { get; set; }
        #endregion

        #region CustomsReleasedDate
        public abstract class customsReleasedDate : BqlDateTime.Field<customsReleasedDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Customs Released")]
        public DateTime? CustomsReleasedDate { get; set; }
        #endregion

        #region DeliveredDate
        public abstract class deliveredDate : BqlDateTime.Field<deliveredDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Delivered On")]
        public DateTime? DeliveredDate { get; set; }
        #endregion

        // Demurrage / free-time tracking
        #region LastFreeDay
        public abstract class lastFreeDay : BqlDateTime.Field<lastFreeDay> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Last Free Day")]
        public DateTime? LastFreeDay { get; set; }
        #endregion

        #region DemurrageDailyRate
        public abstract class demurrageDailyRate : BqlDecimal.Field<demurrageDailyRate> { }
        [PXDBDecimal(4)]
        [PXUIField(DisplayName = "Demurrage $/Day")]
        public decimal? DemurrageDailyRate { get; set; }
        #endregion

        // Freight forwarder / broker
        #region FreightForwarderID
        public abstract class freightForwarderID : BqlInt.Field<freightForwarderID> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Forwarder")]
        [PXSelector(typeof(Search<UsrFreightForwarder.forwarderID,
            Where<UsrFreightForwarder.active, Equal<True>>>),
            typeof(UsrFreightForwarder.forwarderCD),
            typeof(UsrFreightForwarder.name),
            SubstituteKey = typeof(UsrFreightForwarder.forwarderCD))]
        public int? FreightForwarderID { get; set; }
        #endregion

        #region BrokerID
        public abstract class brokerID : BqlInt.Field<brokerID> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Customs Broker")]
        [PXSelector(typeof(Search<UsrCustomsBroker.brokerID,
            Where<UsrCustomsBroker.active, Equal<True>>>),
            typeof(UsrCustomsBroker.brokerCD),
            typeof(UsrCustomsBroker.description),
            SubstituteKey = typeof(UsrCustomsBroker.brokerCD))]
        public int? BrokerID { get; set; }
        #endregion

        // CBP entry capture
        #region EntryNumber
        public abstract class entryNumber : BqlString.Field<entryNumber> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Entry #")]
        public string EntryNumber { get; set; }
        #endregion

        #region EntryType
        public abstract class entryType : BqlString.Field<entryType> { }
        [PXDBString(2, IsUnicode = true)]
        [PXUIField(DisplayName = "Entry Type")]
        [PXStringList(new string[] { "01", "03", "11", "23" },
                       new string[] { "01 - Consumption", "03 - AD/CVD", "11 - Informal", "23 - Temporary" })]
        public string EntryType { get; set; }
        #endregion

        #region EntryReleaseDate
        public abstract class entryReleaseDate : BqlDateTime.Field<entryReleaseDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Entry Released")]
        public DateTime? EntryReleaseDate { get; set; }
        #endregion

        #region DutyPaid
        public abstract class dutyPaid : BqlDecimal.Field<dutyPaid> { }
        [PXDBDecimal(4)]
        [PXUIField(DisplayName = "Duty Paid")]
        public decimal? DutyPaid { get; set; }
        #endregion

        #region MPFAmount
        public abstract class mPFAmount : BqlDecimal.Field<mPFAmount> { }
        [PXDBDecimal(4)]
        [PXUIField(DisplayName = "MPF")]
        public decimal? MPFAmount { get; set; }
        #endregion

        #region HMFAmount
        public abstract class hMFAmount : BqlDecimal.Field<hMFAmount> { }
        [PXDBDecimal(4)]
        [PXUIField(DisplayName = "HMF")]
        public decimal? HMFAmount { get; set; }
        #endregion

        // ISF filing
        #region ISFFiledDate
        public abstract class iSFFiledDate : BqlDateTime.Field<iSFFiledDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "ISF Filed")]
        public DateTime? ISFFiledDate { get; set; }
        #endregion

        #region ISFFilingNbr
        public abstract class iSFFilingNbr : BqlString.Field<iSFFilingNbr> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "ISF #")]
        public string ISFFilingNbr { get; set; }
        #endregion

        // Unbound calculated fields for grid + tile rendering
        #region RiskLevel
        public abstract class riskLevel : BqlString.Field<riskLevel> { }
        [PXString(1)]
        [PXUIField(DisplayName = "●", Enabled = false)]
        public string RiskLevel { get; set; }
        #endregion

        #region DaysToLFD
        public abstract class daysToLFD : BqlInt.Field<daysToLFD> { }
        [PXInt]
        [PXUIField(DisplayName = "LFD (days)", Enabled = false)]
        public int? DaysToLFD { get; set; }
        #endregion

        #region DemurrageExposure
        public abstract class demurrageExposure : BqlDecimal.Field<demurrageExposure> { }
        [PXDecimal(2)]
        [PXUIField(DisplayName = "$ Exposure", Enabled = false)]
        public decimal? DemurrageExposure { get; set; }
        #endregion

        #region DocsRequiredCount
        public abstract class docsRequiredCount : BqlInt.Field<docsRequiredCount> { }
        [PXInt]
        [PXUIField(DisplayName = "Docs Required", Enabled = false)]
        public int? DocsRequiredCount { get; set; }
        #endregion

        #region DocsReceivedCount
        public abstract class docsReceivedCount : BqlInt.Field<docsReceivedCount> { }
        [PXInt]
        [PXUIField(DisplayName = "Docs Received", Enabled = false)]
        public int? DocsReceivedCount { get; set; }
        #endregion

        #region DocsSummary
        public abstract class docsSummary : BqlString.Field<docsSummary> { }
        [PXString(10)]
        [PXUIField(DisplayName = "Docs", Enabled = false)]
        public string DocsSummary { get; set; }
        #endregion

        // --- 2026-04-08: Phase D — Timeline + tab count fields (unbound, per-row) ---
        #region TimelineHtml
        public abstract class timelineHtml : BqlString.Field<timelineHtml> { }
        [PXString(8000)]
        [PXUIField(DisplayName = "Timeline", Enabled = false)]
        public string TimelineHtml { get; set; }
        #endregion

        #region EventsCount
        public abstract class eventsCount : BqlInt.Field<eventsCount> { }
        [PXInt]
        [PXUIField(DisplayName = "Events", Enabled = false)]
        public int? EventsCount { get; set; }
        #endregion

        #region POLinksCount
        public abstract class pOLinksCount : BqlInt.Field<pOLinksCount> { }
        [PXInt]
        [PXUIField(DisplayName = "POs", Enabled = false)]
        public int? POLinksCount { get; set; }
        #endregion

        #region POLinksTotal
        public abstract class pOLinksTotal : BqlDecimal.Field<pOLinksTotal> { }
        [PXDecimal(2)]
        [PXUIField(DisplayName = "PO Total", Enabled = false)]
        public decimal? POLinksTotal { get; set; }
        #endregion

        #region CostsCount
        public abstract class costsCount : BqlInt.Field<costsCount> { }
        [PXInt]
        [PXUIField(DisplayName = "Costs", Enabled = false)]
        public int? CostsCount { get; set; }
        #endregion

        #region CostsTotal
        public abstract class costsTotal : BqlDecimal.Field<costsTotal> { }
        [PXDecimal(2)]
        [PXUIField(DisplayName = "Costs Total", Enabled = false)]
        public decimal? CostsTotal { get; set; }
        #endregion

        #region TabLabelsJson
        public abstract class tabLabelsJson : BqlString.Field<tabLabelsJson> { }
        [PXString(500)]
        // 2026-04-08: Visible=false hides the field server-side so Acumatica
        // never emits a label cell for it. The SB501000.aspx template tried
        // to hide this with Style="display:none;" on edTabLabelsJson, but that
        // left "Tab Labels:" + the raw JSON value visible in prod because the
        // auto-layout wraps the control in a label+value row regardless.
        // PR #295 added a PXLayoutRule + SuppressLabel to frmTimeline to fix
        // it at the ASPX level, but the ASPX never landed in prod (--no-merge
        // bug — see project_no_merge_aspx_bug.md — skips ASPX extraction for
        // co-published projects). Server-side Visible=false ships via the DLL
        // (Phase 1 of publish), bypassing the --no-merge bug. The JS tab
        // label updater targets the control's DOM id which is still emitted.
        [PXUIField(DisplayName = "Tab Labels", Enabled = false, Visible = false)]
        public string TabLabelsJson { get; set; }
        #endregion
        // --- end 2026-04-08 additions ---

        #region NoteID
        public abstract class noteID : BqlGuid.Field<noteID> { }
        [PXNote]
        public Guid? NoteID { get; set; }
        #endregion

        #region CreatedByID
        public abstract class createdByID : BqlGuid.Field<createdByID> { }
        [PXDBCreatedByID]
        public Guid? CreatedByID { get; set; }
        #endregion

        #region CreatedDateTime
        public abstract class createdDateTime : BqlDateTime.Field<createdDateTime> { }
        [PXDBCreatedDateTime]
        public DateTime? CreatedDateTime { get; set; }
        #endregion

        #region LastModifiedByID
        public abstract class lastModifiedByID : BqlGuid.Field<lastModifiedByID> { }
        [PXDBLastModifiedByID]
        public Guid? LastModifiedByID { get; set; }
        #endregion

        #region LastModifiedDateTime
        public abstract class lastModifiedDateTime : BqlDateTime.Field<lastModifiedDateTime> { }
        [PXDBLastModifiedDateTime]
        public DateTime? LastModifiedDateTime { get; set; }
        #endregion

        #region Tstamp
        public abstract class tstamp : BqlByteArray.Field<tstamp> { }
        [PXDBTimestamp]
        public byte[] Tstamp { get; set; }
        #endregion
    }
}
