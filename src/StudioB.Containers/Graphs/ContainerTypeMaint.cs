using PX.Data;
using PX.Data.BQL.Fluent;

namespace StudioB.Containers
{
    public class ContainerTypeMaint : PXGraph<ContainerTypeMaint, UsrContainerType>
    {
        public SelectFrom<UsrContainerType>.View ContainerType;
    }
}
