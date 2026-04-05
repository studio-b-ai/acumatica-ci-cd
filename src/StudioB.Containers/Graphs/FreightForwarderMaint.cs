using PX.Data;
using PX.Data.BQL.Fluent;

namespace StudioB.Containers
{
    public class FreightForwarderMaint : PXGraph<FreightForwarderMaint, UsrFreightForwarder>
    {
        public SelectFrom<UsrFreightForwarder>.View Forwarder;
    }
}
