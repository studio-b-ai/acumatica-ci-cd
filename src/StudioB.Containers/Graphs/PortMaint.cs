using PX.Data;
using PX.Data.BQL.Fluent;

namespace StudioB.Containers
{
    public class PortMaint : PXGraph<PortMaint, UsrPort>
    {
        public SelectFrom<UsrPort>.View Port;
    }
}
