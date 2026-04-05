using PX.Data;

namespace StudioB.Containers
{
    public class ContainerPrefsMaint : PXGraph<ContainerPrefsMaint>
    {
        public PXSelect<UsrContainerPrefs> Prefs;

        protected virtual void _(Events.RowInserted<UsrContainerPrefs> e)
        {
            if (e.Row != null && e.Row.PrefsID == null)
                e.Row.PrefsID = 1;
        }
    }
}
