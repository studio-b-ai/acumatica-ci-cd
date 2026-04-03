using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.PO;

namespace StudioB.PO
{
    public class POOrderEntry_RelationsExt : PXGraphExtension<POOrderEntry>
    {
        public static bool IsActive() => true;

        public PXSelect<UsrPORelation,
            Where<UsrPORelation.refNoteID, Equal<Current<POOrder.noteID>>>> Relations;

        public PXSelect<UsrPOActivity,
            Where<UsrPOActivity.refNoteID, Equal<Current<POOrder.noteID>>>,
            OrderBy<Desc<UsrPOActivity.createdDateTime>>> Activities;
    }
}
