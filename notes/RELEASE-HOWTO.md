# ViewVC Release HowTo

## Branch Management

Primary ViewVC development occurs on `master` branch, with bugfixes
and compatible features being backported to maintenance branches
associated with minor release streams as appropriate.  When, however,
the need arises to create a new maintenance branch, the process is as
follows:

1.  Checkout and pull `master` so it is up-to-date.

    > $ git checkout master; git pull

2.  Create and push the maintenance branch.

    > $ git checkout -b X.Y.x; git push --set-upstream origin HEAD

3.  Checkout `master` again.

    > $ git checkout master

4.  Modify files on `master` which refer to the version number of the
    release stream, updating them to the desired new values.

    * `CHANGES`:  Add stub section for new release.
    * `INSTALL`:  Update example configuration.
    * `lib/viewvc.py`:  Update the `__version__` value.
    * `docs/upgrading-howto.html`:  Add stub section for new release.
    * `docs/template-authoring-guide.html`:  Update to reflect new release.

5.  Commit those changes.

    > $ git commit -a -m "Begin new release stream for X.Y."

## Release Process

ViewVC rolls releases from maintenance branches associate with each
minor version of the software.  For example, the 1.1.0 release is rolled
from the 1.1.x branch.  The same is true for 1.1.1, 1.1.2, and so on.

The script `tools/make-release` creates the release archive files that
we distribute.  All other steps required to get a ViewVC release out
of the door require manual execution.

Those steps are as follows:

1.  Checkout and pull the maintenance branch for the release you
    intend to roll.

    > $ git checkout X.Y.x; git pull

2.  Review any open bug reports.

    > https://github.com/viewvc/viewvc/issues

3.  Prepare the release branch.

    * Create a local release branch.

        > $ git checkout -b X.Y.Z-release

    * Add a new subsection to `docs/upgrading.html` describing all
      user visible changes for users of previous releases of ViewVC.
      NOTE: This step should not be necessary for patch releases.

    * Verify that copyright years are correct in both the `LICENSE`
      file and the source code.

    * Update the `CHANGES` file, pegging the date of the release.

    * Update `lib/viewvc.py`, removing "-dev" from the `__version__`
      variable value.
    
    * Test, test, test!  There is no automatic testsuite available.
      So just try different permutations of `viewvc.conf`
      settings... and pray.  Fix what needs fixin', keeping the
      `CHANGES` file in sync with the branch.

    * When the branch is ready for release, commit it.

        > $ git commit -a -m "Prepare for the X.Y.Z release"

4.  At this point, the source code committed to the release branch
    should exactly reflect what you wish to distribute and dub "the
    release".  It's time to tag to release and push the tag upstream.

    > $ git tag X.Y.Z; git push origin tag X.Y.Z

5.  Now, we need to prep the maintenance branch for the next release.

    * Switch to the maintenance branch.

        > $ git checkout X.Y.x
  
    * Merge the changes you made on the release branch.

        > $ git merge X.Y.Z-release
        
    * Edit `lib/viewvc.py` to increment the patch number of the
      `__version__` variable and re-add the "-dev" suffix.

    * Edit `CHANGES` and add the template for the next release's
      changes.

    * Commit and push those changes.

        > $ git commit -a -m "Begin a new release cycle."; git push

    * Remove the release branch.

        > $ git branch -d X.Y.Z-release

6.  Go into an empty directory and run the `make-release` script:

    > $ tools/make-release viewvc-X.Y.Z tags/X.Y.Z

7.  Verify the archive files:

    * do they have a LICENSE.html file?
    * do they have necessary include documentation?
    * do they *not* have unnecessary stuff?
    * do they install and work correctly?

8.  Upload the release archive files (tar.gz and zip) to
    http://viewvc.org/downloads and update the website's
    `downloads/index.html` to list them.

9.  Edit the Issues tracker's Milestones, closing the Milestone for the current
    release, and adding a new Milestone for the next patch release.

    > https://github.com/viewvc/viewvc/milestones

10. Copy the `CHANGES` entries for this release into the `CHANGES`
    file for newer release lines and commit.

11. Edit the GitHub release (at https://github.com/viewvc/viewvc/releases/tag/X.Y.Z):

    * Change the release title to "ViewVC X.Y.Z"
 
    * Copy the `CHANGES` entries for the release into the description:

        ```
        ChangeLog:
         
          * Did some stuff.
          * Fixed some bugs.
         ```
         
    * Attach the release archive files (tar.gz and zip) to the release.

        
