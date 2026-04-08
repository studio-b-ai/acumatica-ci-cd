using PX.Data;
using PX.Data.BQL.Fluent;

namespace StudioB.Containers
{
    /// <summary>
    /// Simple maintenance graph for <see cref="UsrCustomsBroker"/>.
    /// Backs the SB302040 screen.
    /// </summary>
    public class CustomsBrokerMaint : PXGraph<CustomsBrokerMaint, UsrCustomsBroker>
    {
        public SelectFrom<UsrCustomsBroker>.View Broker;
    }
}
